#!/usr/bin/env python3
"""Generate one `klt gen mos_array` block per PFET of the sampling front end
(issue #122), and carry the single source of truth for *which n-well domain*
each of those PFETs belongs to.

Scope: this flow draws the sampling front end's **PFETs only** -- the nine
`sky130_fd_pr__pfet_01v8` instances of `design/sampling_frontend.sch`. It is
deliberately not the whole sub-block (that is #99); it is the composition
study #122 asks for, whose entire subject is the n-well/body-tie structure,
which only the PFETs have. Every NFET in that schematic ties its body to the
p-substrate and is a non-issue for well isolation (`klt extract` synthesizes
one shared substrate net for NMOS bodies regardless of drawn geometry -- see
`layout/comparator/README.md`'s "Body ties" note).

Why the domain table lives in a shared module rather than in `build_layout.py`
-------------------------------------------------------------------------------
`design/sampling_frontend.sch`'s decision record DR-004 requires a
*non-standard* PFET body tie: `Sa_p`/`Se_p` tie their body to `BOOST_P` and
`Sa_n`/`Se_n` to `BOOST_N` -- a boosted node that rises above VDD during
sampling -- while every other PFET in the block (`Scp_*`, `Cmswp_*`, `Invp`)
ties body to VDD normally. A VDD-tied body on `Sa`/`Se` forward-biases their
drain/body junction once BOOST exceeds VDD by a diode drop, so the body tie
is load-bearing circuit behaviour, not a layout nicety.

In layout that requirement is *only* expressible as physical geometry: a
PMOS's body terminal is whatever net the tap inside its own n-well island
carries (`klt extract`'s sky130 deck derives the PMOS body from
`active & nwell` and names it from the tap that reaches that island). So
"which body net" and "which n-well island" are the same fact, and it is
recorded once, as ``DOMAIN`` on each device row of `layout/bin/
_pfet_devices.py`'s shared ``PFET_DEVICES`` table (imported here as
``DEVICES``, and by `layout/sampling-frontend/bin/gen_blocks.py` as
``PFET_DEVICES`` -- see issue #208) -- `build_layout.py` reads it to decide
both the well partition and the tap net, and `render-record.py` re-derives
the expected body net from it when asserting the extracted result.

Device sizing is a 1:1 transcription of
`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` (the
xschem-derived, already-simulated device fragment for
`design/sampling_frontend.sch`), device by device -- this script decides only
*how* each schematic PFET is drawn, never *what* its electrical size is.

Drawing style: every device is a `mos_array` 1x1 with ``dummy: 0`` and
``gate_contact: true``. No `diff_pair`, no interleaving, no dummies: unlike
`layout/comparator/`, none of these nine devices is a matched pair -- they are
nine functionally distinct switches, so there is no matching claim to make and
spending `splits`/common-centroid effort here would be effort spent on
nothing. `mos_array` 1x1 is chosen for the same reason `layout/comparator/`
chose it for its unmatched tail switch: it reuses the same validated
unit-device primitive (contact/landing-pad geometry) every other flow in this
repo already relies on.

No guard rings (`guard_ring` is not called at all). `klt gen guard_ring
--params '{"add_well": true}'` does draw a tap ring inside its own well, which
is *nearly* the primitive this issue needs -- but its well tie ties to
whatever the caller routes the ring to, and a closed ring around a device
blocks routing to every port inside it (the finding
`layout/comparator/bin/gen_blocks.py`'s docstring already records). The
well/tap islands here are therefore drawn by `build_layout.py` through
`klt draw` instead; see that module's docstring for the recipe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _pfet_devices import DOMAIN_TAP_NET, PFET_DEVICES as DEVICES  # noqa: E402

#: Nets promoted to top-level pins.  Every net in this cell is external to it
#: (it is a PFET-only slice of a larger schematic), so all fourteen are ports.
PIN_NETS = (
    "VDD",
    "SAMPLE",
    "SAMPLEB",
    "VINP",
    "VINN",
    "VCM",
    "BOOST_P",
    "BOOST_N",
    "G_P",
    "G_N",
    "BSBOT_P",
    "BSBOT_N",
    "BPREF_P",
    "BPREF_N",
)


def block_params(w_um: float, l_um: float) -> dict:
    """`klt gen mos_array` params for one unmatched PFET switch."""
    return {
        "w_um": w_um,
        "l_um": l_um,
        "fingers": 1,
        "rows": 1,
        "cols": 1,
        "dummy": 0,
        "flavor": "pfet",
        "gate_contact": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="directory to write <id>.gds/<id>.json into")
    parser.add_argument("--klt", default="klt", help="path to the klt executable")
    parser.add_argument("--pdk", default="sky130A", help="PDK variant")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for block_id, schematic_name, _domain, w_um, l_um, *_nets in DEVICES:
        gds_path = args.out_dir / f"{block_id}.gds"
        json_path = args.out_dir / f"{block_id}.json"
        cmd = [
            args.klt,
            "gen",
            "mos_array",
            "--params",
            json.dumps(block_params(w_um, l_um)),
            "--pdk",
            args.pdk,
            "--cell-name",
            schematic_name.upper(),
            "-o",
            str(gds_path),
            "--format",
            "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        json_path.write_text(result.stdout)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(
                f"gen_blocks.py: {block_id}: non-JSON output:\n{result.stdout}\n{result.stderr}",
                file=sys.stderr,
            )
            return 1
        if report.get("error"):
            print(f"gen_blocks.py: {block_id}: generator error: {report['error']}", file=sys.stderr)
            return 1
        print(
            f"gen_blocks.py: wrote {json_path} "
            f"({report.get('device_count')} device, W={w_um}u L={l_um}u)"
        )

    print(f"gen_blocks.py: generated {len(DEVICES)} blocks in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

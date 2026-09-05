#!/usr/bin/env python3
"""Generate every `klt gen` block the sampling front end's full layout
(issue #99) composes: nine PFETs (the three-domain n-well partition #122
proved, `layout/sampling-frontend-wells/`), eleven NFETs, and the two
MiM-capacitor pairs.

Device sizing is a 1:1 transcription of
`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` (the
xschem-derived, already-simulated device list for
`design/sampling_frontend.sch`) -- this script decides only *how* each
schematic device is drawn (generator, matching topology), never *what* its
electrical size is. That SPICE fragment, not the schematic's raw drawn
coordinates, is the ground truth for every D/G/S/(top/bottom) net below: it is
xschem's own netlister output, so it is immune to a raw-coordinate misread of
the `.sch` file's pin placement.

Three device groups
--------------------
* **PFET domain set (`PFET_DEVICES`)** -- unchanged from
  `layout/sampling-frontend-wells/bin/gen_blocks.py`: nine `mos_array` 1x1
  PFETs, each tagged with the n-well domain (`boost_p`/`vdd`/`boost_n`) its
  body tie belongs to per DR-004/DR-007. `build_layout.py` reads `domain` to
  reproduce the exact three-island recipe #122 verified, rather than
  re-deriving it.
* **NFET set (`NFET_DEVICES`)** -- eleven NFETs, all drawn `mos_array` 1x1
  (`dummy: 0`, `gate_contact: true`), including the differential input pair
  `Msw_p`/`Msw_n`.

  Matching strategy for `Msw_p`/`Msw_n`, stated explicitly per this issue's
  own acceptance criterion (common-mode definition is sensitive to switch
  mismatch): a prior Builder investigation of this issue recommended
  `klt gen diff_pair` for this specific pair, since
  `design/sampling_frontend.sch`'s header calls the input switches out by
  name as setting common-mode definition. This increment does **not** use
  `diff_pair` for them, and the reason is a floorplan fact rather than a
  disagreement with that recommendation: `diff_pair`'s two legs (Q1/Q2) are
  drawn **vertically stacked at the same local x** (one leg's D/G/S ports sit
  directly above the other's), which is exactly wrong for this sub-block's
  routing scheme (`build_layout.py`'s single shared met2 track per net) --
  two different nets (`Msw_p`'s and `Msw_n`'s D/G/S) would need to route
  through the same x column, forcing per-pin offset hacks that (measured
  directly, building this layout) produce cascading column collisions with
  *other* devices' columns rather than a clean, verifiable result. Every
  other block in this layout (all nine PFETs, the other nine NFETs) is a
  plain `mos_array` 1x1 side-by-side single, so `Msw_p`/`Msw_n` as two
  side-by-side `mos_array` singles is consistent with the rest of the
  floorplan and keeps the routing scheme uniform and verifiable. This is a
  **documented, deliberate deferral**, not a silent drop: a `diff_pair`
  (or hand-composed common-centroid) treatment for `Msw_p`/`Msw_n` remains
  open follow-up work, argued out in this directory's `README.md` under
  "The matching / dummy strategy" and filed generically upstream as
  `2AMLogic/klayout-tools#1495`, and does not
  block this issue's own DRC/LVS-clean acceptance criteria (which this
  layout meets with plain, unmatched placement, the same way
  `layout/sampling-frontend-wells/` makes no matching claim for its own nine
  PFETs).
* **Capacitor set (`CAP_DEVICES`)** -- two `cap_array` calls, `num=2` each, so
  every one of the four MiM caps this schematic instantiates
  (`Cboot_p`/`Cboot_n`, W=L=9.8um; `Csamp_p`/`Csamp_n`, W=L=46.9um) is drawn as
  one leg of `cap_array`'s own matched unit pair rather than as two
  independent generator calls. Each differential pair of caps
  (`Cboot_p`/`Cboot_n`, `Csamp_p`/`Csamp_n`) is a *matched* pair in the
  circuit sense -- a plate-area mismatch between the two sides is a
  differential offset -- so drawing each pair from a single `num=2`
  generator call, which emits two units of identical drawn geometry at a
  fixed pitch, is worth the zero extra cost it takes.

No guard rings anywhere -- `mos_array`/`cap_array` do not offer one, and
`klt gen guard_ring` is deliberately not composed around any of these
blocks. Same reason `layout/comparator/bin/gen_blocks.py` and
`layout/sampling-frontend-wells/bin/gen_blocks.py` both give: a closed ring
blocks routing to every port inside it. PFET/NFET body ties come from
`build_layout.py`'s own drawn n-well/substrate taps instead (see that
module's docstring).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

#: The three n-well domains the PFETs partition into, mapped to the net each
#: domain's well tap is routed to -- unchanged from issue #122's own recipe.
DOMAIN_TAP_NET = {
    "boost_p": "BOOST_P",
    "vdd": "VDD",
    "boost_n": "BOOST_N",
}

#: One row per `sky130_fd_pr__pfet_01v8` instance, transcribed from
#: `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`'s
#: `X<name> D G S B sky130_fd_pr__pfet_01v8 L=.. W=..` cards. Identical to
#: `layout/sampling-frontend-wells/bin/gen_blocks.py`'s own `DEVICES` table --
#: this is the same nine devices, the same recipe, reused rather than
#: re-derived.
#:
#: (block id, schematic name, domain, W um, L um, D net, G net, S net)
PFET_DEVICES = [
    ("sa_p", "Sa_p", "boost_p", 1.0, 0.5, "BOOST_P", "SAMPLE", "VDD"),
    ("se_p", "Se_p", "boost_p", 1.0, 0.15, "G_P", "SAMPLEB", "BOOST_P"),
    ("scp_p", "Scp_p", "vdd", 1.0, 0.15, "BSBOT_P", "SAMPLEB", "VINP"),
    ("cmswp_p", "Cmswp_p", "vdd", 1.0, 0.15, "BPREF_P", "SAMPLEB", "VCM"),
    ("invp", "Invp", "vdd", 2.0, 0.15, "SAMPLEB", "SAMPLE", "VDD"),
    ("cmswp_n", "Cmswp_n", "vdd", 1.0, 0.15, "BPREF_N", "SAMPLEB", "VCM"),
    ("scp_n", "Scp_n", "vdd", 1.0, 0.15, "BSBOT_N", "SAMPLEB", "VINN"),
    ("se_n", "Se_n", "boost_n", 1.0, 0.15, "G_N", "SAMPLEB", "BOOST_N"),
    ("sa_n", "Sa_n", "boost_n", 1.0, 0.5, "BOOST_N", "SAMPLE", "VDD"),
]

#: One row per `sky130_fd_pr__nfet_01v8` instance, including `Msw_p`/`Msw_n`
#: (see the matching-strategy note above for why they are plain singles here,
#: not a `diff_pair`), transcribed the same way.
#:
#: (block id, schematic name, W um, L um, D net, G net, S net)
NFET_DEVICES = [
    ("msw_p", "Msw_p", 2.0, 0.15, "VINP", "G_P", "TOP_P"),
    ("msw_n", "Msw_n", 2.0, 0.15, "VINN", "G_N", "TOP_N"),
    ("sb_p", "Sb_p", 1.0, 0.15, "BSBOT_P", "SAMPLEB", "GND"),
    ("scn_p", "Scn_p", 1.0, 0.15, "BSBOT_P", "SAMPLE", "VINP"),
    ("sd_p", "Sd_p", 1.0, 0.5, "G_P", "SAMPLEB", "GND"),
    ("cmswn_p", "Cmswn_p", 1.0, 0.15, "BPREF_P", "SAMPLE", "VCM"),
    ("cmswn_n", "Cmswn_n", 1.0, 0.15, "BPREF_N", "SAMPLE", "VCM"),
    ("sd_n", "Sd_n", 1.0, 0.5, "G_N", "SAMPLEB", "GND"),
    ("scn_n", "Scn_n", 1.0, 0.15, "BSBOT_N", "SAMPLE", "VINN"),
    ("sb_n", "Sb_n", 1.0, 0.15, "BSBOT_N", "SAMPLEB", "GND"),
    ("invn", "Invn", 1.0, 0.15, "SAMPLEB", "SAMPLE", "GND"),
]

#: The two matched capacitor pairs. (block id, plate side um, leg table).
#: Leg table: (cap_array unit index, schematic name, top-plate net (`_TOP`
#: port), bottom-plate net (`_BOT` port)).
CAP_DEVICES = [
    (
        "cboot",
        9.8,
        [
            (0, "Cboot_p", "BOOST_P", "BSBOT_P"),
            (1, "Cboot_n", "BOOST_N", "BSBOT_N"),
        ],
    ),
    (
        "csamp",
        46.9,
        [
            (0, "Csamp_p", "TOP_P", "BPREF_P"),
            (1, "Csamp_n", "TOP_N", "BPREF_N"),
        ],
    ),
]


def _run(
    klt: str, pdk: str, generator: str, params: dict, cell_name: str, gds_path: Path
) -> tuple[str, str]:
    cmd = [
        klt,
        "gen",
        generator,
        "--params",
        json.dumps(params),
        "--pdk",
        pdk,
        "--cell-name",
        cell_name,
        "-o",
        str(gds_path),
        "--format",
        "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.stdout, result.stderr


def _write_and_check(block_id: str, stdout: str, stderr: str, json_path: Path) -> dict | None:
    json_path.write_text(stdout)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"gen_blocks.py: {block_id}: non-JSON output:\n{stdout}\n{stderr}", file=sys.stderr)
        return None
    if report.get("error"):
        print(f"gen_blocks.py: {block_id}: generator error: {report['error']}", file=sys.stderr)
        return None
    return report


def pfet_params(w_um: float, l_um: float) -> dict:
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


def nfet_params(w_um: float, l_um: float) -> dict:
    return {
        "w_um": w_um,
        "l_um": l_um,
        "fingers": 1,
        "rows": 1,
        "cols": 1,
        "dummy": 0,
        "flavor": "nfet",
        "gate_contact": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="directory to write <id>.gds/<id>.json into")
    parser.add_argument("--klt", default="klt", help="path to the klt executable")
    parser.add_argument("--pdk", default="sky130A", help="PDK variant")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ok = True

    for block_id, name, _domain, w_um, l_um, *_nets in PFET_DEVICES:
        stdout, stderr = _run(
            args.klt, args.pdk, "mos_array", pfet_params(w_um, l_um), name.upper(),
            args.out_dir / f"{block_id}.gds",
        )
        report = _write_and_check(block_id, stdout, stderr, args.out_dir / f"{block_id}.json")
        ok = ok and report is not None
        if report:
            print(f"gen_blocks.py: {block_id} (pfet {w_um}/{l_um}um): {report.get('device_count')} device")

    for block_id, name, w_um, l_um, *_nets in NFET_DEVICES:
        stdout, stderr = _run(
            args.klt, args.pdk, "mos_array", nfet_params(w_um, l_um), name.upper(),
            args.out_dir / f"{block_id}.gds",
        )
        report = _write_and_check(block_id, stdout, stderr, args.out_dir / f"{block_id}.json")
        ok = ok and report is not None
        if report:
            print(f"gen_blocks.py: {block_id} (nfet {w_um}/{l_um}um): {report.get('device_count')} device")

    for block_id, plate_um, _legs in CAP_DEVICES:
        cap_params = {"plate_w_um": plate_um, "plate_h_um": plate_um, "num": 2, "spacing_um": 0.5}
        stdout, stderr = _run(
            args.klt, args.pdk, "cap_array", cap_params, block_id.upper(), args.out_dir / f"{block_id}.gds"
        )
        report = _write_and_check(block_id, stdout, stderr, args.out_dir / f"{block_id}.json")
        ok = ok and report is not None
        if report:
            print(f"gen_blocks.py: {block_id} (cap_array {plate_um}x{plate_um}um, num=2): {report.get('device_count')} devices")

    total_blocks = len(PFET_DEVICES) + len(NFET_DEVICES) + len(CAP_DEVICES)
    print(f"gen_blocks.py: generated {total_blocks} blocks in {args.out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

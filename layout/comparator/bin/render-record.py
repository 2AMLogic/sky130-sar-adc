#!/usr/bin/env python3
"""Render layout/comparator/reports/<record-id>/record.md from the `klt` JSON
envelopes run-flow.sh just wrote into that directory.

Standard library only (matching sim/harness/'s no-extra-runtime-dependency
convention).

Exits non-zero -- *after* writing record.md, so the evidence trail still
carries a record of the failure -- if any of the six expected verdicts do not
hold:

  1. every one of the five `klt gen` matched device/pair blocks is
     independently DRC-clean before composition
  2. DRC on the composed comparator layout is clean
  3. LVS reports "match" against the known-good reference
  4. LVS reports "mismatch" against the device-parameter negative control
  5. LVS reports "mismatch" against the topology negative control
  6. extraction reports no unbiased PMOS body net -- i.e. the drawn n-well tie
     really does bias every PMOS body to VDD, rather than the layout silently
     falling back to KLayout's synthesized `vsubs`/anonymous proxy net

Verdicts 4-5 are the same falsifiability discipline layout/trivial-cell/'s own
flow established for this repo (see layout/bin/render-record.py's docstring):
"match" only means something once "mismatch" has been shown to be reachable on
the same toolchain in the same run, and the two corruption classes are
independent on purpose -- a comparison that only checked connectivity would
pass verdict 4, and one that only compared device parameters would pass
verdict 5.

Verdict 6 is this sub-block's own addition. An LVS-clean result would still be
reachable with `unbiased_pmos_body_nets` non-empty on a reference that declared
the same proxy body net, so the body-tie claim needs its own assertion rather
than riding on the LVS verdict.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _record_common_strict import (  # noqa: E402
    build_argparser_strict,
    git_field,
    load_json_strict,
)

BLOCKS = ("tail", "inpair", "latn", "latp", "rst")

_load = load_json_strict
_git = git_field


def main() -> int:
    ap = build_argparser_strict()
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    block_drc = _load(out_dir / "drc.blocks.json")
    draw = _load(out_dir / "draw.json")
    compose = _load(out_dir / "compose.json")
    route = _load(out_dir / "route.summary.json")
    drc = _load(out_dir / "drc.json")
    extract = _load(out_dir / "extract.json")
    lvs = _load(out_dir / "lvs.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")
    lvs_bad_topo = _load(out_dir / "lvs.broken-topology.json")

    sha = _git(args.repo_root, "rev-parse", "HEAD")
    branch = _git(args.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(args.repo_root, "status", "--porcelain") != ""

    klt_version = subprocess.run(
        [args.klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info = json.loads(
        subprocess.run(
            [args.klt, "pdk", "find", "--pdk", args.pdk_variant, "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    dirty_blocks = sorted(
        block for block in BLOCKS if block_drc.get(block, {}).get("status") != "clean"
    )
    unbiased = extract.get("unbiased_pmos_body_nets") or []

    checks = [
        (
            "every `klt gen` matched device/pair block is DRC-clean in isolation",
            not dirty_blocks,
        ),
        ("DRC on the composed comparator layout is clean", drc.get("status") == "clean"),
        ("LVS matches the known-good reference", lvs.get("status") == "match"),
        (
            "LVS negative control (device-parameter corruption) reports mismatch",
            lvs_bad_dev.get("status") == "mismatch",
        ),
        (
            "LVS negative control (topology corruption) reports mismatch",
            lvs_bad_topo.get("status") == "mismatch",
        ),
        (
            "extraction reports no unbiased PMOS body net "
            "(the drawn n-well tie really biases every PMOS body)",
            not unbiased,
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    counts = lvs.get("counts", {})
    lines: list[str] = []
    a = lines.append
    a(f"# Comparator layout record: {args.record_id}")
    a("")
    a(
        "Physical layout for the dynamic (StrongARM-class) comparator "
        "sub-block of this SAR ADC (issue #101), drawn against "
        "`design/comparator.sch`. Devices come from `klt gen`'s matched "
        "`diff_pair`/`mos_array` generators (see "
        "`layout/comparator/bin/gen_blocks.py` for the matching strategy); "
        "placement and every wire come from "
        "`layout/comparator/bin/build_layout.py`, verified here against the "
        "sky130 DRC deck and the schematic-derived LVS reference."
    )
    a("")
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok in checks:
        a(f"- [{'x' if ok else ' '}] {desc}")
    a("")

    a("## Provenance")
    a("")
    a(f"- `klt` version: {klt_version}")
    a(f"- KLayout engine: {drc.get('provenance', {}).get('klayout_version')}")
    a(f"- PDK: {pdk_info.get('variant')} ({pdk_info.get('version')})")
    a(f"- PDK root: resolved via `{pdk_info.get('resolved_via')}`")
    a(f"- repo commit: `{sha}` on `{branch}`{' (dirty working tree)' if dirty else ''}")
    a(
        f"- DRC deck: `{drc.get('deck')}` "
        f"({drc.get('provenance', {}).get('deck', {}).get('content_hash')})"
    )
    a("")

    a("## Blocks (`klt gen`)")
    a("")
    a("| Block | Cell | Devices | bbox (um) | own DRC |")
    a("| --- | --- | --- | --- | --- |")
    for block in BLOCKS:
        report = _load(out_dir / f"{block}.json")
        bbox = report.get("bbox_um", {})
        a(
            f"| `{block}` | `{report.get('cell_name')}` | "
            f"{report.get('device_count')} | "
            f"{bbox.get('x0')},{bbox.get('y0')} .. {bbox.get('x1')},{bbox.get('y1')} | "
            f"{block_drc.get(block, {}).get('status')} |"
        )
    a("")

    a("## Routing + composition")
    a("")
    a(
        f"- `klt draw` (cell `{draw.get('cell_name')}`): "
        f"{draw.get('shape_count')} shapes, {draw.get('label_count')} pin labels"
    )
    a(
        f"- `klt gen-compose` (cell `{compose.get('cell_name')}`): "
        f"{len(compose.get('blocks', []))} blocks placed at explicit origins, "
        f"bbox {compose.get('bbox_um')}"
    )
    a(
        "- `klt gen-compose` is used as a **placer only** here (no `routing` "
        "block in the request) -- see `build_layout.py`'s module docstring, "
        "and 2AMLogic/klayout-tools#1386 for the generically-filed tool gap "
        "that motivates it."
    )
    a("")

    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        f"| DRC (composed layout) | {drc.get('status')} | "
        f"violation_count={drc.get('violation_count')}, "
        f"rule_counts={drc.get('rule_counts')} |"
    )
    a(
        f"| Extract | {extract.get('status')} | "
        f"device_count={extract.get('device_count')}, "
        f"net_count={extract.get('net_count')}, "
        f"pin_count={extract.get('pin_count')}, "
        f"unbiased_pmos_body_nets={len(unbiased)} |"
    )
    a(
        f"| LVS (good reference) | {lvs.get('status')} | "
        f"devices {counts.get('devices', {}).get('matched')}/"
        f"{counts.get('devices', {}).get('reference')} matched, "
        f"nets {counts.get('nets', {}).get('matched')}/"
        f"{counts.get('nets', {}).get('reference')} matched, "
        f"pins {counts.get('pins', {}).get('matched')}/"
        f"{counts.get('pins', {}).get('reference')} matched |"
    )
    a(
        f"| LVS (device-parameter negative control) | {lvs_bad_dev.get('status')} | "
        f"mismatch_count={lvs_bad_dev.get('mismatch_count')}, "
        f"categories={lvs_bad_dev.get('category_counts')} |"
    )
    a(
        f"| LVS (topology negative control) | {lvs_bad_topo.get('status')} | "
        f"mismatch_count={lvs_bad_topo.get('mismatch_count')}, "
        f"categories={lvs_bad_topo.get('category_counts')} |"
    )
    a("")

    a("## Differential routing symmetry")
    a("")
    a(
        "Device matching alone does not fix a dynamic comparator's offset: its "
        "decision is a race between OUTP and OUTN, so unequal wire capacitance "
        "on the two output nodes biases that race the same way a device "
        "mismatch would. `build_layout.py` routes each negative-half branch on "
        "the mirror image of its positive-half counterpart's own y-track where "
        "that track is free (see its `MIRROR_PIN`), and the numbers below are "
        "what that actually achieved -- measured from the drawn geometry, not "
        "asserted. They are *not* a parasitic extraction; wire area is a proxy "
        "for wire capacitance, and a real `klt pex` pass on this sub-block "
        "would supersede them."
    )
    a("")
    a("| Pair | wire area (um^2) | delta | imbalance |")
    a("| --- | --- | --- | --- |")
    for entry in route.get("differential_symmetry", []):
        pos, neg = entry["pair"]
        area_pos, area_neg = entry["wire_area_um2"]
        a(
            f"| {pos} / {neg} | {area_pos} / {area_neg} | "
            f"{entry['delta_um2']} um^2 | {entry['delta_percent']}% |"
        )
    a("")
    a("Per-net wiring:")
    a("")
    a("| Net | met1 (um^2) | met2 (um^2) | vias | mcons |")
    a("| --- | --- | --- | --- | --- |")
    for net, metrics in sorted(route.get("nets", {}).items()):
        a(
            f"| {net} | {metrics['met1_area_um2']} | {metrics['met2_area_um2']} | "
            f"{metrics['via_count']} | {metrics['mcon_count']} |"
        )
    a("")

    a("## Net correspondence (layout <-> reference)")
    a("")
    for entry in lvs.get("net_correspondence", []):
        marker = "pin" if entry.get("pin") else "internal"
        a(f"- `{entry.get('layout')}` <-> `{entry.get('reference')}` ({marker})")
    a("")

    a("## Reported LVS findings")
    a("")
    findings = lvs.get("mismatches", [])
    if not findings:
        a("- none")
    for finding in findings:
        a(
            f"- [{finding.get('severity')}] {finding.get('category')}: "
            f"{finding.get('description')}"
        )
    if lvs.get("status") == "match":
        a("")
        a(
            "Every finding above is reported at `severity: warning` with "
            "`error_count = 0`; `klt lvs`'s own overall verdict for this run is "
            f"`{lvs.get('status')}`."
        )
    a("")

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

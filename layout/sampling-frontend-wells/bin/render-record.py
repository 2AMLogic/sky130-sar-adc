#!/usr/bin/env python3
"""Render layout/sampling-frontend-wells/reports/<record-id>/record.md from
the `klt` JSON envelopes run-flow.sh just wrote into that directory.

Standard library only (matching sim/harness/'s no-extra-runtime-dependency
convention).

Exits non-zero -- *after* writing record.md, so the evidence trail still
carries a record of the failure -- if any of the ten expected verdicts do not
hold:

  1. every `klt gen` PFET block is independently DRC-clean before composition
  2. `klt drc --deck sky130` on the composed layout is clean
  3. the composed layout is clean against sky130's own n-well rules
     (nwell.1 / nwell.2a / difftap.8 / difftap.10, run through
     `klt drc --engine klayout --deck-file drc/nwell_isolation.drc`)
  4. that same well deck reports VIOLATIONS on the deliberately-illegal
     fixture, naming nwell.2a among them -- without which verdict 3 would be
     indistinguishable from a deck that matched nothing
  5. `klt drc --deck sky130` reports the same fixture CLEAN -- the recorded,
     reproducible evidence for why verdict 3 needs its own deck at all
  6. `klt precheck` passes (geometry hygiene; pin labels land on drawn metal)
  7. extraction reports no unbiased PMOS body net
  8. extraction reports each PFET's body on the net its own n-well island's
     tap is routed to -- Sa/Se on BOOST_P/BOOST_N, everything else on VDD
  9. LVS reports "match" against reference.spice
 10. LVS reports "mismatch" against BOTH negative controls (body-tie
     corruption, device-parameter corruption)

Verdict 8 is the one issue #122 exists to answer, and verdict 10's body-tie
control is what stops verdict 9 from being circular: an LVS "match" against a
reference that declared the wrong body would prove only that the comparison
ignores the body column. Verdicts 4-5 apply the same falsifiability
discipline to DRC that layout/trivial-cell/ established for this repo
(issue #2) -- "clean" means nothing until "violations" is shown reachable on
the same deck in the same run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _record_common_strict import (  # noqa: E402
    build_argparser_strict,
    git_field,
    load_json_strict,
)
from gen_blocks import DEVICES, DOMAIN_TAP_NET  # noqa: E402

BLOCKS = tuple(row[0] for row in DEVICES)

#: schematic device name -> the body net its n-well island must produce.
EXPECTED_BODY = {row[1]: DOMAIN_TAP_NET[row[2]] for row in DEVICES}

#: schematic device name -> (source net, gate net, drain net), used to line an
#: extracted device up with its schematic counterpart without relying on
#: KLayout's anonymous `$n` device naming.
DEVICE_KEY = {(row[5], row[6], row[7]): row[1] for row in DEVICES}

_load = load_json_strict
_git = git_field


def _extracted_bodies(extract: dict) -> tuple[dict[str, str], list[str]]:
    """Map schematic device name -> extracted body net.

    Keyed on the (source, gate, drain) net triple rather than on the extracted
    device name, because `klt extract` names devices `$1..$9` in geometric
    order. Any device whose triple is not in the schematic table is reported
    as unrecognised rather than silently ignored.
    """
    bodies: dict[str, str] = {}
    unrecognised: list[str] = []
    for device in extract.get("devices", []):
        nets = device.get("nets", {})
        key = (nets.get("s"), nets.get("g"), nets.get("d"))
        name = DEVICE_KEY.get(key)
        if name is None:
            unrecognised.append(f"{device.get('name')} {key}")
            continue
        bodies[name] = nets.get("b")
    return bodies, unrecognised


def main() -> int:
    ap = build_argparser_strict()
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    block_drc = _load(out_dir / "drc.blocks.json")
    draw = _load(out_dir / "draw.json")
    compose = _load(out_dir / "compose.json")
    wells = _load(out_dir / "wells.summary.json")
    drc = _load(out_dir / "drc.json")
    drc_wells = _load(out_dir / "drc.wells.json")
    drc_wells_fixture = _load(out_dir / "drc.wells.fixture.json")
    drc_curated_fixture = _load(out_dir / "drc.curated.fixture.json")
    precheck = _load(out_dir / "precheck.json")
    extract = _load(out_dir / "extract.json")
    lvs = _load(out_dir / "lvs.json")
    lvs_bad_body = _load(out_dir / "lvs.broken-body-tie.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")

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
    bodies, unrecognised = _extracted_bodies(extract)
    body_wrong = sorted(
        name for name, expected in EXPECTED_BODY.items() if bodies.get(name) != expected
    )
    precheck_failed = sorted(
        check.get("check")
        for check in precheck.get("checks", [])
        if check.get("status") == "fail"
    )

    checks = [
        (
            "every `klt gen` PFET block is DRC-clean in isolation",
            not dirty_blocks,
        ),
        (
            "`klt drc --deck sky130` on the composed layout is clean",
            drc.get("status") == "clean",
        ),
        (
            "the composed layout is clean against sky130's own n-well rules "
            "(nwell.1 / nwell.2a / difftap.8 / difftap.10)",
            drc_wells.get("status") == "clean",
        ),
        (
            "DRC negative control: the illegal fixture reports violations "
            "naming `nwell.2a` on that same well deck",
            drc_wells_fixture.get("status") == "violations"
            and "nwell.2a" in (drc_wells_fixture.get("rule_counts") or {}),
        ),
        (
            "gap evidence: `klt drc --deck sky130` reports that same illegal "
            "fixture CLEAN (it carries no n-well rules)",
            drc_curated_fixture.get("status") == "clean",
        ),
        (
            "`klt precheck` passes (geometry hygiene; every pin label lands "
            "on drawn metal)",
            not precheck_failed,
        ),
        (
            "extraction reports no unbiased PMOS body net",
            not unbiased,
        ),
        (
            "extraction reports every PFET body on its own n-well island's "
            "tap net (Sa/Se -> BOOST_P/BOOST_N, the rest -> VDD)",
            not body_wrong and not unrecognised,
        ),
        ("LVS matches the known-good reference", lvs.get("status") == "match"),
        (
            "LVS negative control (body-tie corruption: Sa/Se bodies moved to "
            "VDD) reports mismatch",
            lvs_bad_body.get("status") == "mismatch",
        ),
        (
            "LVS negative control (device-parameter corruption) reports mismatch",
            lvs_bad_dev.get("status") == "mismatch",
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    counts = lvs.get("counts", {})
    lines: list[str] = []
    a = lines.append
    a(f"# Sampling front end n-well isolation record: {args.record_id}")
    a("")
    a(
        "Physical composition of the sampling front end's PFET set into "
        "**three electrically distinct n-well islands** (issue #122), drawn "
        "against `design/sampling_frontend.sch` and its DR-004 body-tie "
        "requirement: `Sa_p`/`Se_p` tie their body to `BOOST_P`, "
        "`Sa_n`/`Se_n` to `BOOST_N`, and the remaining five PFETs to `VDD`. "
        "Devices come from `klt gen mos_array`; the well partition, the taps "
        "and every wire come from "
        "`layout/sampling-frontend-wells/bin/build_layout.py`."
    )
    a("")
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok in checks:
        a(f"- [{'x' if ok else ' '}] {desc}")
    a("")
    if dirty_blocks:
        a(f"Blocks not clean in isolation: {', '.join(dirty_blocks)}")
        a("")
    if unrecognised:
        a(f"Extracted devices not matched to a schematic device: {unrecognised}")
        a("")
    if precheck_failed:
        a(f"Failed precheck checks: {', '.join(precheck_failed)}")
        a("")

    a("## Provenance")
    a("")
    a(f"- `klt` version: {klt_version}")
    a(f"- KLayout engine: {drc.get('provenance', {}).get('klayout_version')}")
    a(f"- PDK: {pdk_info.get('variant')} ({pdk_info.get('version')})")
    a(f"- PDK root: resolved via `{pdk_info.get('resolved_via')}`")
    a(f"- repo commit: `{sha}` on `{branch}`{' (dirty working tree)' if dirty else ''}")
    a(
        f"- curated DRC deck: `{drc.get('deck')}` "
        f"({drc.get('provenance', {}).get('deck', {}).get('content_hash')})"
    )
    a(
        f"- n-well DRC deck: `{Path(str(drc_wells.get('deck'))).name}` "
        f"({drc_wells.get('provenance', {}).get('deck', {}).get('content_hash')})"
    )
    a("")

    a("## The n-well partition (the deliverable)")
    a("")
    a(
        "One drawn `nwell` rectangle per body-tie domain, each merging only "
        "its own devices' generator-drawn local wells and each holding one "
        "`tap` routed to that domain's net. `nwell.2a` (sky130's minimum "
        f"n-well spacing) is {wells.get('nwell_2a_rule_um')} um; the drawn "
        f"separation is {wells.get('well_gap_drawn_um')} um."
    )
    a("")
    a("| Island | tap net | schematic devices | n-well x range (um) | tap (um) |")
    a("| --- | --- | --- | --- | --- |")
    for domain in wells.get("domains", []):
        well = domain["well_um"]
        tap = domain["tap_um"]
        a(
            f"| `{domain['id']}` | **{domain['tap_net']}** | "
            f"{', '.join(domain['schematic_devices'])} | "
            f"{well['x0']} .. {well['x1']} | "
            f"{tap['x0']}..{tap['x1']} x {tap['y0']}..{tap['y1']} |"
        )
    a("")
    a(f"Island-to-island gaps: {wells.get('island_gaps_um')} um.")
    a("")

    a("## Extracted body terminals")
    a("")
    a(
        "`klt extract --deck sky130` derives a PMOS body from the `nwell` "
        "island the device actually sits in, named by whatever the tap inside "
        "that island is routed to. No `nwell.pin` (64/5) well label is drawn "
        "anywhere in this layout, deliberately: a drawn label would name the "
        "well even if the tap routing were broken, which would make this "
        "table a tautology instead of a measurement."
    )
    a("")
    a("| Schematic device | island | expected body | extracted body | |")
    a("| --- | --- | --- | --- | --- |")
    for _bid, name, domain, *_rest in DEVICES:
        expected = EXPECTED_BODY[name]
        got = bodies.get(name)
        a(
            f"| `{name}` | `{domain}` | {expected} | "
            f"{got} | {'OK' if got == expected else 'WRONG'} |"
        )
    a("")
    a(f"`unbiased_pmos_body_nets`: {len(unbiased)} entr{'y' if len(unbiased) == 1 else 'ies'}.")
    a("")

    a("## Blocks (`klt gen mos_array`)")
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

    a("## Composition")
    a("")
    a(
        f"- `klt draw` (cell `{draw.get('cell_name')}`): "
        f"{draw.get('shape_count')} shapes, {draw.get('label_count')} pin labels "
        "(the three n-well islands, their taps, every wire)"
    )
    a(
        f"- `klt gen-compose` (cell `{compose.get('cell_name')}`): "
        f"{len(compose.get('blocks', []))} blocks placed at explicit origins, "
        f"bbox {compose.get('bbox_um')}"
    )
    a(
        "- `klt gen-compose` is used as a **placer only** (no `routing` block "
        "in the request), the same choice `layout/comparator/` documents."
    )
    a("")

    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        f"| DRC, curated deck (composed layout) | {drc.get('status')} | "
        f"violation_count={drc.get('violation_count')}, "
        f"rule_counts={drc.get('rule_counts')} |"
    )
    a(
        f"| DRC, n-well deck (composed layout) | {drc_wells.get('status')} | "
        f"violation_count={drc_wells.get('violation_count')}, "
        f"rule_counts={drc_wells.get('rule_counts')} |"
    )
    a(
        f"| DRC, n-well deck (illegal fixture) | {drc_wells_fixture.get('status')} | "
        f"violation_count={drc_wells_fixture.get('violation_count')}, "
        f"rule_counts={drc_wells_fixture.get('rule_counts')} |"
    )
    a(
        f"| DRC, curated deck (same illegal fixture) | "
        f"{drc_curated_fixture.get('status')} | "
        f"violation_count={drc_curated_fixture.get('violation_count')} -- the "
        "curated deck carries no n-well rules, which is why the deck above "
        "exists |"
    )
    a(
        f"| precheck | {precheck.get('status')} | "
        f"{len(precheck.get('checks', []))} checks, "
        f"{len(precheck_failed)} failed |"
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
        f"| LVS (body-tie negative control) | {lvs_bad_body.get('status')} | "
        f"mismatch_count={lvs_bad_body.get('mismatch_count')}, "
        f"categories={lvs_bad_body.get('category_counts')} |"
    )
    a(
        f"| LVS (device-parameter negative control) | {lvs_bad_dev.get('status')} | "
        f"mismatch_count={lvs_bad_dev.get('mismatch_count')}, "
        f"categories={lvs_bad_dev.get('category_counts')} |"
    )
    a("")

    a("## Net correspondence (layout <-> reference)")
    a("")
    for entry in lvs.get("net_correspondence", []):
        marker = "pin" if entry.get("pin") else "internal"
        a(f"- `{entry.get('layout')}` <-> `{entry.get('reference')}` ({marker})")
    a("")

    a("## Reported LVS findings (good reference)")
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
            f"`error_count = {lvs.get('error_count')}`; `klt lvs`'s own overall "
            f"verdict for this run is `{lvs.get('status')}`."
        )
    a("")

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

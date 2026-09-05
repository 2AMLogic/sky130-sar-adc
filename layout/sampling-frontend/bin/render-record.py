#!/usr/bin/env python3
"""Render layout/sampling-frontend/reports/<record-id>/record.md from the `klt`
JSON envelopes run-flow.sh just wrote into that directory.

Standard library only (matching sim/harness/'s no-extra-runtime-dependency
convention).

Exits non-zero -- *after* writing record.md, so the evidence trail still
carries a record of the failure -- if any of the eleven expected verdicts do
not hold:

  1. every `klt gen` block is independently DRC-clean before composition
  2. `klt drc --deck sky130` on the composed layout is clean
  3. that SAME deck reports VIOLATIONS, naming `nwell.space.1`, on the
     deliberately-illegal n-well fixture -- without which verdict 2 would be
     indistinguishable from a deck that carries no well rules at all (which
     is precisely what klt 0.3.0's curated deck did)
  4. `klt precheck` passes (geometry hygiene; pin labels land on drawn metal)
  5. extraction reports the schematic's exact device population
     (11 nfet + 9 pfet + 4 MiM caps, and nothing else)
  6. extraction reports NO single-terminal net
  7. extraction reports no unbiased PMOS body net
  8. extraction reports each PFET's body on the net its own n-well island's
     tap is routed to -- Sa/Se on BOOST_P/BOOST_N, the other five on VDD
  9. LVS reports "match" against reference.spice
 10. LVS reports "mismatch" against the body-tie negative control
 11. LVS reports "mismatch" against the device-parameter and capacitor
     top-plate negative controls

Verdicts 3, 6, 10 and 11 are the falsifiability discipline
layout/trivial-cell/ established for this repo (issue #2), each specialised to
a failure mode this sub-block can actually suffer:

* verdict 6 is the cheap, legible guard against the exact defect this layout
  hit while being built -- a MiM capacitor's top plate silently extracting as
  an isolated net. LVS catches it too, but as a diffuse net/device mismatch;
  `single_terminal_nets[]` names it in one line.
* verdict 8 is what stops verdict 7 from being satisfied by the single
  VDD-tied well DR-004 forbids, which would also report
  `unbiased_pmos_body_nets: []`.
* verdict 10 is what stops verdict 9 from being an artefact of a comparison
  that ignores the body column.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_blocks import (  # noqa: E402
    CAP_DEVICES,
    DOMAIN_TAP_NET,
    NFET_DEVICES,
    PFET_DEVICES,
)

BLOCKS = tuple(
    row[0] for row in list(PFET_DEVICES) + list(NFET_DEVICES) + list(CAP_DEVICES)
)

#: schematic device name -> the body net its n-well island must produce.
EXPECTED_BODY = {row[1]: DOMAIN_TAP_NET[row[2]] for row in PFET_DEVICES}

#: schematic PFET name -> ((drain, gate, source) nets, (W um, L um)). The net
#: triple is `PFET_DEVICES`' own column order; W/L are carried alongside it
#: because the nets alone are NOT unique once the internal ones extract
#: anonymously (`Sa_p` and `Se_p` both touch BOOST_P and differ only in L).
#: See `_extracted_bodies` for the two tolerances the match needs.
PFET_KEY = {
    row[1]: ((row[5], row[6], row[7]), (row[3], row[4])) for row in PFET_DEVICES
}

#: The device population design/sampling_frontend.sch instantiates.
EXPECTED_DEVICE_COUNTS = {
    "nfet": len(NFET_DEVICES),
    "pfet": len(PFET_DEVICES),
    "sky130_fd_pr__model__cap_mim": sum(len(row[2]) for row in CAP_DEVICES),
}


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _anonymous(net: str | None) -> bool:
    """True for a net `klt extract` could not name -- KLayout's `\\$n`."""
    return net is None or net.lstrip("\\").startswith("$")


def _extracted_bodies(extract: dict) -> tuple[dict[str, str], list[str]]:
    """Map schematic PFET name -> extracted body net.

    Keyed on the terminal nets rather than on the extracted device name,
    because `klt extract` names devices `$1..$24` in geometric order. Two
    tolerances the match needs, both properties of the extractor rather than
    of this layout:

    * **Anonymous nets are wildcards.** Only eleven of this cell's seventeen
      nets carry a drawn pin label; the internal ones (`SAMPLEB`, `G_P`,
      `G_N`, `BSBOT_P`, `BSBOT_N`) come back as `\\$n`.
    * **Source and drain may be swapped.** A MOSFET is symmetric and nothing
      in the drawn geometry distinguishes the two diffusions, so the
      extractor's D/S assignment is not required to agree with the
      schematic's. The gate is matched positionally; the drain/source pair is
      matched as an unordered pair.

    Because the nets alone are not enough to tell `Sa_p` from `Se_p` once
    `G_P`/`SAMPLEB` extract anonymously, the drawn W/L is matched too. A PFET
    matching no schematic row, more than one row, or a row already claimed by
    an earlier device is reported as unrecognised rather than silently
    ignored.
    """
    bodies: dict[str, str] = {}
    unrecognised: list[str] = []

    def fits(
        got_nets: tuple[str | None, str | None, str | None],
        got_wl: tuple[float | None, float | None],
        want: tuple[tuple[str, str, str], tuple[float, float]],
    ) -> bool:
        (want_d, want_g, want_s), (want_w, want_l) = want
        got_w, got_l = got_wl
        if got_w is None or abs(got_w - want_w) > 1e-6:
            return False
        if got_l is None or abs(got_l - want_l) > 1e-6:
            return False
        got_d, got_g, got_s = got_nets
        if not (_anonymous(got_g) or got_g == want_g):
            return False
        return any(
            (_anonymous(a) or a == want_d) and (_anonymous(b) or b == want_s)
            for a, b in ((got_d, got_s), (got_s, got_d))
        )

    for device in extract.get("devices", []):
        if device.get("class") != "pfet":
            continue
        nets = device.get("nets", {})
        params = device.get("params", {})
        got_nets = (nets.get("d"), nets.get("g"), nets.get("s"))
        got_wl = (params.get("w_um"), params.get("l_um"))
        candidates = [
            name for name, want in PFET_KEY.items() if fits(got_nets, got_wl, want)
        ]
        if len(candidates) != 1 or candidates[0] in bodies:
            unrecognised.append(
                f"{device.get('name')} nets={got_nets} w/l={got_wl} -> {candidates}"
            )
            continue
        bodies[candidates[0]] = nets.get("b")
    return bodies, unrecognised


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--pdk-variant", required=True)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    block_drc = _load(out_dir / "drc.blocks.json")
    draw = _load(out_dir / "draw.json")
    compose = _load(out_dir / "compose.json")
    summary = _load(out_dir / "layout.summary.json")
    drc = _load(out_dir / "drc.json")
    drc_fixture = _load(out_dir / "drc.fixture.json")
    precheck = _load(out_dir / "precheck.json")
    extract = _load(out_dir / "extract.json")
    lvs = _load(out_dir / "lvs.json")
    lvs_bad_body = _load(out_dir / "lvs.broken-body-tie.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")
    lvs_bad_top = _load(out_dir / "lvs.broken-topology.json")

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
    single_terminal = extract.get("single_terminal_nets") or []
    device_counts = extract.get("device_counts") or {}
    bodies, unrecognised = _extracted_bodies(extract)
    body_wrong = sorted(
        name for name, expected in EXPECTED_BODY.items() if bodies.get(name) != expected
    )
    precheck_failed = sorted(
        str(check.get("check"))
        for check in precheck.get("checks", [])
        if check.get("status") == "fail"
    )
    fixture_rules = drc_fixture.get("rule_counts") or {}

    checks = [
        (
            "every `klt gen` block is DRC-clean in isolation",
            not dirty_blocks,
        ),
        (
            "`klt drc --deck sky130` on the composed layout is clean",
            drc.get("status") == "clean",
        ),
        (
            "DRC negative control: the deliberately-illegal n-well fixture "
            "reports violations naming `nwell.space.1` on that same deck",
            drc_fixture.get("status") == "violations"
            and "nwell.space.1" in fixture_rules,
        ),
        (
            "`klt precheck` passes (geometry hygiene; every pin label lands "
            "on drawn metal)",
            not precheck_failed,
        ),
        (
            "extraction reports the schematic's exact device population "
            f"({EXPECTED_DEVICE_COUNTS})",
            device_counts == EXPECTED_DEVICE_COUNTS,
        ),
        (
            "extraction reports no single-terminal net (every drawn terminal "
            "reaches the net the schematic puts it on)",
            not single_terminal,
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
            "LVS negative control (body-tie corruption: the four boosted "
            "bodies moved to VDD) reports mismatch",
            lvs_bad_body.get("status") == "mismatch",
        ),
        (
            "LVS negative controls (device-parameter corruption; capacitor "
            "top-plate net corruption) both report mismatch",
            lvs_bad_dev.get("status") == "mismatch"
            and lvs_bad_top.get("status") == "mismatch",
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    counts = lvs.get("counts", {})
    coverage = drc.get("coverage") or {}
    lines: list[str] = []
    a = lines.append
    a(f"# Sampling front end layout record: {args.record_id}")
    a("")
    a(
        "Physical layout for the sampling front end sub-block of this SAR ADC "
        "(issue #99), drawn against `design/sampling_frontend.sch`: eleven "
        "NFETs (including the `Msw_p`/`Msw_n` input switch pair), nine PFETs "
        "partitioned into the three isolated n-well body-tie domains DR-004 / "
        "DR-007 require, and four MiM capacitors, plus every wire between "
        "them. Devices come from `klt gen mos_array`/`klt gen cap_array`; the "
        "well partition, the substrate tap, the floorplan and all routing come "
        "from `layout/sampling-frontend/bin/build_layout.py`."
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
        a(f"Extracted PFETs not matched to a schematic device: {unrecognised}")
        a("")
    if single_terminal:
        a(f"Single-terminal nets: {single_terminal}")
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
        f"- DRC deck: `{drc.get('deck')}` "
        f"({drc.get('provenance', {}).get('deck', {}).get('content_hash')})"
    )
    a(f"- deliverable: `{drc.get('file')}`")
    a("")

    a("## The n-well partition (DR-004 / DR-007)")
    a("")
    a(
        "One drawn `nwell` rectangle per body-tie domain, each merging only "
        "its own devices' generator-drawn local wells and each holding one "
        "`tap` routed to that domain's net -- the recipe issue #122 proved in "
        "`layout/sampling-frontend-wells/`, reused here unchanged. "
        f"`nwell.space.1` (sky130's minimum n-well spacing) is "
        f"{summary.get('nwell_2a_rule_um')} um; the drawn separation is "
        f"{summary.get('well_gap_drawn_um')} um."
    )
    a("")
    a("| Island | tap net | schematic devices | n-well x range (um) | tap (um) |")
    a("| --- | --- | --- | --- | --- |")
    for domain in summary.get("domains", []):
        well = domain["well_um"]
        tap = domain["tap_um"]
        a(
            f"| `{domain['id']}` | **{domain['tap_net']}** | "
            f"{', '.join(domain['schematic_devices'])} | "
            f"{well['x0']} .. {well['x1']} | "
            f"{tap['x0']}..{tap['x1']} x {tap['y0']}..{tap['y1']} |"
        )
    a("")
    a(f"Island-to-island gaps: {summary.get('island_gaps_um')} um.")
    a(
        f"p-substrate tap (routed to GND): {summary.get('substrate_tap_um')} um."
    )
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
    for _bid, name, domain, *_rest in PFET_DEVICES:
        expected = EXPECTED_BODY[name]
        got = bodies.get(name)
        a(
            f"| `{name}` | `{domain}` | {expected} | "
            f"{got} | {'OK' if got == expected else 'WRONG'} |"
        )
    a("")
    a(
        f"`unbiased_pmos_body_nets`: {len(unbiased)} "
        f"entr{'y' if len(unbiased) == 1 else 'ies'}. "
        f"`single_terminal_nets`: {len(single_terminal)}."
    )
    a("")
    a(
        "The eleven NFET bodies are **not** in this table on purpose: the "
        "curated deck synthesizes one global substrate net (`vsubs`) for them "
        "regardless of drawn geometry, so `klt lvs` reports "
        "`device.body_unverified` for all eleven and no drawn tap can change "
        "that. What the drawn p-substrate tap does do is merge this layout's "
        "`GND` conductor into `vsubs`, without which `GND` would extract as a "
        "separate net and LVS would not match at all."
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

    a("## Composition")
    a("")
    a(
        f"- `klt draw` (cell `{draw.get('cell_name')}`): "
        f"{draw.get('shape_count')} shapes, {draw.get('label_count')} pin labels "
        "(the three n-well islands, the substrate tap, every wire)"
    )
    a(
        f"- `klt gen-compose` (cell `{compose.get('cell_name')}`): "
        f"{len(compose.get('blocks', []))} blocks placed at explicit origins, "
        f"bbox {compose.get('bbox_um')}"
    )
    a(
        "- `klt gen-compose` is used as a **placer only** (no `routing` block "
        "in the request), the same choice `layout/comparator/` and "
        "`layout/sampling-frontend-wells/` both document."
    )
    a(
        f"- row x ranges (um): PFETs {summary.get('row1_x_range_um')}, "
        f"NFETs {summary.get('row2_x_range_um')}, "
        f"caps {summary.get('row3_x_range_um')}; shared met2 track band starts "
        f"at y = {summary.get('track_y0_um')} um"
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
        f"| DRC, curated deck (illegal n-well fixture) | "
        f"{drc_fixture.get('status')} | "
        f"violation_count={drc_fixture.get('violation_count')}, "
        f"rule_counts={fixture_rules} |"
    )
    a(
        f"| precheck | {precheck.get('status')} | "
        f"{len(precheck.get('checks', []))} checks, "
        f"{len(precheck_failed)} failed |"
    )
    a(
        f"| Extract | {extract.get('status')} | "
        f"device_count={extract.get('device_count')} {device_counts}, "
        f"net_count={extract.get('net_count')}, "
        f"pin_count={extract.get('pin_count')}, "
        f"unbiased_pmos_body_nets={len(unbiased)}, "
        f"single_terminal_nets={len(single_terminal)} |"
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
    for label, envelope in (
        ("body-tie", lvs_bad_body),
        ("device-parameter", lvs_bad_dev),
        ("capacitor top-plate", lvs_bad_top),
    ):
        a(
            f"| LVS ({label} negative control) | {envelope.get('status')} | "
            f"mismatch_count={envelope.get('mismatch_count')}, "
            f"categories={envelope.get('category_counts')} |"
        )
    a("")

    a("## DRC coverage (what the deck did and did not check)")
    a("")
    a(
        "Recorded straight from `klt drc`'s own `coverage` block rather than "
        "asserted in prose, so a later deck release changing it shows up as a "
        "diff in the next record."
    )
    a("")
    a(f"- rule families in scope: {coverage.get('deck_scope')}")
    a(f"- layers checked: {coverage.get('layers_checked')}")
    a(
        "- layers present in the stream with **no** rule: "
        f"{coverage.get('layers_in_stream_without_rules')}"
    )
    a(f"- rules skipped (layer absent from the stream): {coverage.get('rules_skipped')}")
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

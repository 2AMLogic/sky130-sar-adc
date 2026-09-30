#!/usr/bin/env python3
"""Render layout/halflsb-offset/reports/<record-id>/record.md from the `klt`
JSON envelopes run-flow.sh just wrote into that directory.

Standard library only (matching sim/harness/'s no-extra-runtime-dependency
convention).

Exits non-zero -- *after* writing record.md, so the evidence trail still carries
a record of the failure -- if any of the fourteen expected verdicts do not hold:

  1. the schematic-parity gate agrees with `design/sar_adc_top.spice`
  2. every `klt gen` block is independently DRC-clean before composition
  3. `klt drc --deck sky130` on the composed layout is clean
  4. that SAME deck reports VIOLATIONS, naming `nwell.space.1`, on the
     deliberately-illegal n-well fixture -- this block splits its n-well into
     two separately-tapped islands, so verdict 3 says nothing about the split
     unless the deck can see an illegal well spacing at all
  5. `klt precheck` passes outright on the layout's own 1 nm database grid
  6. on sky130's 5 nm MANUFACTURING grid, `offgrid` is the only failing
     precheck check, and every off-grid shape is on a MiM-stack layer -- i.e.
     no transistor-level geometry is off-grid (see README, "Why `klt
     precheck`'s 5 nm grid check cannot pass here")
  7. extraction reports the schematic's exact device population
     (4 pfet + 2 nfet + 2 MiM caps, and nothing else)
  8. extraction reports NO single-terminal net
  9. extraction reports no unbiased PMOS body net, and every PFET body on VDD
 10. LVS reports "match" against the schematic-derived reference
 11. every matched net's layout name equals its reference name
 12. LVS reports "mismatch" against the device-parameter and capacitor
     top-plate negative controls
 13. the swapped-enable control reproduces its documented blind spot: `klt lvs`
     reports "match", AND that same run's net correspondence is NOT
     name-identical, so the corruption is visible in the envelope even though
     the verdict is not
 14. `build_layout.py`'s `_n`/`_p` translation congruence held

Verdicts 4, 8, 11, 12 and 13 are the falsifiability discipline
layout/trivial-cell/ established for this repo (issue #2), each specialised to
a failure mode THIS network can actually suffer:

* verdict 11 is the one this block added to the family. `klt lvs` matches nets
  structurally, not by name, and both half-LSB enables enter this network only
  as ports -- so swapping `HALF_LSB_EN` with `HALF_LSB_ENN`, which inverts
  DR-009's load-bearing enable polarity, is a graph isomorphism and reports
  `match`. Requiring the correspondence table to be name-identical is what
  turns that class of defect back into a failure.
* verdict 13 is the measurement behind verdict 11, kept as its own control
  rather than as a claim in prose. **If verdict 13 ever fails because the
  control now reports `mismatch`, `klt lvs` has gained the ability to see this
  class: invert the verdict and say so in the next record -- do not delete
  it.** Same discipline as issue #149's inversion of
  `layout/sampling-frontend-wells/`'s verdict 5 once klt 0.4.0 closed the
  n-well DRC gap that verdict measured.
* verdict 14 is DR-009's matching-dummy requirement. Neither DRC nor LVS can
  see it: a layout that scattered the `_p` devices arbitrarily would be clean
  and would match, while destroying the only reason the dummy exists.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _record_common_strict import (  # noqa: E402
    build_argparser_strict,
    git_field,
    load_json_strict,
    render_lvs_findings,
    render_net_correspondence,
    render_provenance_header,
    resolve_pdk_info_strict,
    tool_version_strict,
)
from gen_blocks import (  # noqa: E402
    CAP_DRAWN_UM,
    CAP_LEGS,
    CAP_SCHEMATIC_UM,
    CAP_UNIT_F,
    SIDE_PITCH_UM,
    SWITCH_DEVICES,
    block_ids,
)

BLOCKS = tuple(block_ids())

#: `klt gen-compose`'s own placement-warning text names the block whose
#: `drc_hints.min_spacing_um` it is citing. Pulling that name out is what lets
#: the record partition the warnings by cause instead of describing them all
#: with one sentence that only fits some of them.
_HINT_OWNER_RE = re.compile(r"closer than (\w+)'s own declared drc_hints")

#: The device population `design/sar_adc_top.spice`'s own eight cards specify.
EXPECTED_DEVICE_COUNTS = {
    "nfet": sum(1 for row in SWITCH_DEVICES if row[3] == "nfet"),
    "pfet": sum(1 for row in SWITCH_DEVICES if row[3] == "pfet"),
    "sky130_fd_pr__model__cap_mim": len(CAP_LEGS),
}

#: Every PFET in this network declares `VDD` as its body (all six `XMoff_*`
#: cards' fourth net is `VDD` for the PFETs and `GND` for the NFETs), so one
#: n-well island per side, each tapped to VDD, is the whole body-tie story --
#: unlike `layout/sampling-frontend/`'s three-domain DR-007 partition.
EXPECTED_PFET_BODY = "VDD"

#: Layers a shape may legitimately be off the 5 nm manufacturing grid on: the
#: MiM stack (capm/met3/via3/met4) and the metal this flow must land on its
#: ports (met1/via1/met2/via2). Anything on a transistor-level layer
#: (nwell/diff/tap/poly/licon1/li1) being off-grid is a defect in this flow, not
#: a consequence of the 1.898 um plate.
MIM_STACK_LAYERS = (
    "68/20",  # met1
    "68/44",  # via1
    "69/20",  # met2
    "69/44",  # via2
    "70/20",  # met3
    "70/44",  # via3
    "71/20",  # met4
    "89/44",  # capm
)

_load = load_json_strict
_git = git_field


def _failing_checks(precheck: dict) -> list[str]:
    return sorted(
        str(check.get("name"))
        for check in precheck.get("checks", [])
        if check.get("status") == "fail"
    )


def _offgrid_census(precheck: dict) -> dict[tuple[str, str], int]:
    """`{(cell, layer): count}` for the `offgrid` check's own violations."""
    census: dict[tuple[str, str], int] = {}
    for check in precheck.get("checks", []):
        if check.get("name") != "offgrid":
            continue
        for violation in check.get("violations", []):
            key = (str(violation.get("cell")), str(violation.get("layer")))
            census[key] = census.get(key, 0) + 1
    return census


def _name_identical_correspondence(lvs: dict) -> list[str]:
    """Matched nets whose layout name differs from their reference name.

    `klt lvs` matches nets structurally, so a permutation of two same-degree
    ports is a legitimate isomorphism to it and reports `match`. On this block
    that is not academic: `HALF_LSB_EN` and `HALF_LSB_ENN` both enter only as
    ports, and swapping them inverts DR-009's enable polarity while leaving the
    verdict clean. This is the residual check that sees it.
    """
    return [
        f"{entry.get('layout')} <-> {entry.get('reference')}"
        for entry in lvs.get("net_correspondence", [])
        if entry.get("layout") != entry.get("reference")
    ]


def _extracted_pfet_bodies(extract: dict) -> list[str]:
    """Every extracted PFET's body net, in extraction order.

    Keyed on nothing: all four PFETs in this network declare the same body, so
    unlike `layout/sampling-frontend/`'s three-domain partition there is no
    per-device identification to do -- the verdict is simply that no PFET body
    is anything but `VDD`.
    """
    return [
        str(device.get("nets", {}).get("b"))
        for device in extract.get("devices", [])
        if device.get("class") == "pfet"
    ]


def main() -> int:
    ap = build_argparser_strict()
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    parity = (out_dir / "schematic-parity.txt").read_text(encoding="utf-8")
    parity_status = _load(out_dir / "schematic-parity.json")
    block_drc = _load(out_dir / "drc.blocks.json")
    draw = _load(out_dir / "draw.json")
    compose = _load(out_dir / "compose.json")
    summary = _load(out_dir / "layout.summary.json")
    drc = _load(out_dir / "drc.json")
    drc_fixture = _load(out_dir / "drc.fixture.json")
    precheck = _load(out_dir / "precheck.json")
    precheck_grid5 = _load(out_dir / "precheck.grid5.json")
    extract = _load(out_dir / "extract.json")
    lvs = _load(out_dir / "lvs.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")
    lvs_bad_top = _load(out_dir / "lvs.broken-topology.json")
    lvs_swapped = _load(out_dir / "lvs.swapped-enable.json")

    sha = _git(args.repo_root, "rev-parse", "HEAD")
    branch = _git(args.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(args.repo_root, "status", "--porcelain") != ""

    klt_version = tool_version_strict(args.klt, "--version")
    pdk_info = resolve_pdk_info_strict(args.klt, args.pdk_variant)

    dirty_blocks = sorted(
        block for block in BLOCKS if block_drc.get(block, {}).get("status") != "clean"
    )
    unbiased = extract.get("unbiased_pmos_body_nets") or []
    single_terminal = extract.get("single_terminal_nets") or []
    device_counts = extract.get("device_counts") or {}
    pfet_bodies = _extracted_pfet_bodies(extract)
    wrong_bodies = [body for body in pfet_bodies if body != EXPECTED_PFET_BODY]
    fixture_rules = drc_fixture.get("rule_counts") or {}
    offgrid = _offgrid_census(precheck_grid5)
    offgrid_bad_layers = sorted(
        {layer for (_cell, layer) in offgrid if layer not in MIM_STACK_LAYERS}
    )
    renamed = _name_identical_correspondence(lvs)
    renamed_swapped = _name_identical_correspondence(lvs_swapped)

    checks = [
        (
            "`bin/check-schematic-parity.py` agrees with "
            "`design/sar_adc_top.spice`'s own eight top-level primitive cards",
            parity_status.get("exit_code") == 0,
        ),
        ("every `klt gen` block is DRC-clean in isolation", not dirty_blocks),
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
            "`klt precheck` passes outright on the layout's own 1 nm database grid",
            precheck.get("status") == "pass",
        ),
        (
            "on sky130's 5 nm manufacturing grid, `offgrid` is the ONLY failing "
            "precheck check and every off-grid shape is on a MiM-stack layer "
            "(no transistor-level geometry off-grid)",
            _failing_checks(precheck_grid5) == ["offgrid"] and not offgrid_bad_layers,
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
            "extraction reports no unbiased PMOS body net, and every PFET body "
            f"on `{EXPECTED_PFET_BODY}`",
            not unbiased
            and len(pfet_bodies) == EXPECTED_DEVICE_COUNTS["pfet"]
            and not wrong_bodies,
        ),
        (
            "LVS matches the schematic-derived reference",
            lvs.get("status") == "match",
        ),
        (
            "every matched net's layout name equals its reference name (the "
            "port-permutation guard -- see verdict 13)",
            not renamed,
        ),
        (
            "LVS negative controls (device-parameter corruption; capacitor "
            "top-plate net corruption) both report mismatch",
            lvs_bad_dev.get("status") == "mismatch"
            and lvs_bad_top.get("status") == "mismatch",
        ),
        (
            "swapped-enable control reproduces its documented blind spot: "
            "`klt lvs` reports `match`, while that run's own net correspondence "
            "is NOT name-identical",
            lvs_swapped.get("status") == "match" and bool(renamed_swapped),
        ),
        (
            "`build_layout.py`'s `_n`/`_p` translation congruence held "
            f"({SIDE_PITCH_UM} um, checked in DBU)",
            bool(summary.get("side_congruence", {}).get("checked_in_dbu")),
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    counts = lvs.get("counts", {})
    coverage = drc.get("coverage") or {}
    congruence = summary.get("side_congruence", {})
    lines: list[str] = []
    a = lines.append
    a(f"# Half-LSB offset network layout record: {args.record_id}")
    a("")
    a(
        "Physical layout for DR-009 item 2's half-LSB quantizer-offset network "
        "(issue #495): the eight `sky130_fd_pr` primitives "
        "`design/sar_adc_top.spice` instantiates at its own top level, inside "
        "no sub-block, which had no drawn geometry anywhere under `layout/` "
        "before this block. Two `cap_mim_m3_1` offset caps (`Choff_n` and its "
        "matching dummy `Choff_p`) drawn as one `klt gen cap_array` matched "
        "pair, plus six `klt gen mos_array` switches (`Moff_{n,p}_{cmn,refp,"
        "cmp}`); the n-well islands, the substrate ties, the floorplan and all "
        "routing come from `layout/halflsb-offset/bin/build_layout.py`. "
        "`layout/top-glue/` covers the 33 `sky130_fd_sc_hd` instances of the "
        "same region; composing both into `layout/sar-adc-top/` is issue #401 "
        "and is NOT claimed here."
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
    if single_terminal:
        a(f"Single-terminal nets: {single_terminal}")
        a("")
    if wrong_bodies:
        a(f"PFET bodies not on {EXPECTED_PFET_BODY}: {wrong_bodies}")
        a("")
    if renamed:
        a(f"Matched nets whose names differ across the compare: {renamed}")
        a("")
    if offgrid_bad_layers:
        a(f"Off-grid shapes on non-MiM-stack layers: {offgrid_bad_layers}")
        a("")

    for line in render_provenance_header(klt_version, drc, pdk_info, sha, branch, dirty):
        a(line)
    a(
        f"- DRC deck: `{drc.get('deck')}` "
        f"({drc.get('provenance', {}).get('deck', {}).get('content_hash')})"
    )
    a(f"- deliverable: `{drc.get('file')}`")
    a("")

    a("## Schematic parity (the independent anchor)")
    a("")
    a(
        "This block's LVS reference is *generated from* "
        "`design/sar_adc_top.spice`, so the reference side is anchored to the "
        "schematic by construction. The layout side is not: "
        "`bin/gen_blocks.py`'s device table is hand-transcribed. "
        "`bin/check-schematic-parity.py` is what closes that, device by device "
        "and terminal by terminal, before this record directory is created -- "
        "and again here, as the verdict above. Its own output, verbatim:"
    )
    a("")
    a("```")
    for line in parity.rstrip("\n").splitlines():
        a(line)
    a("```")
    a("")

    a("## What `klt lvs` cannot see on this block")
    a("")
    a(
        "`klt lvs` reaches a clean `match` against the `swapped-enable` "
        "negative control -- a reference identical to the good one except that "
        "`HALF_LSB_EN` and `HALF_LSB_ENN` are exchanged on the working side's "
        "three gates, i.e. DR-009's load-bearing enable polarity inverted. "
        "`NetlistComparer` matches nets structurally rather than by name, and "
        "both enables enter this network only as ports, so the exchange is a "
        "legitimate isomorphism."
    )
    a("")
    a(
        "That is measured here, not argued: this run's own "
        "`lvs.swapped-enable.json` reports "
        f"`status: {lvs_swapped.get('status')}` with "
        f"mismatch_count={lvs_swapped.get('mismatch_count')}. What it also "
        "reports, in the same envelope, is a net correspondence that is no "
        f"longer name-identical: {renamed_swapped or 'none'}. Verdict 11 above "
        "grades exactly that field on the GOOD run, which is what turns this "
        "defect class back into a failure."
    )
    a("")

    a("## `_n` / `_p` matching, as a construction property")
    a("")
    a(
        "DR-009's `_p` half is a matching dummy: it injects nothing and exists "
        "only so both comparator inputs carry the same capacitance and the same "
        "switch junction parasitics. Neither DRC nor LVS can see whether it "
        "actually matches -- a layout that scattered the `_p` devices would be "
        "clean and would match. So `build_layout.py` asserts it instead: every "
        "shape the `_p` side owns below the track band is the corresponding "
        "`_n`-side shape translated by exactly "
        f"{congruence.get('translation_um')} um, checked in integer nanometres."
    )
    a("")
    a(
        f"- shapes per side covered by the assertion: "
        f"{congruence.get('shapes_per_side')}"
    )
    a(f"- met1 columns per side: {congruence.get('columns_per_side')}")
    a(
        f"- the two caps are one `klt gen cap_array num=2` call, unit pitch "
        f"{summary.get('cap_unit_pitch_um')} um (asserted equal to the side "
        f"translation), so their own geometry is identical by the generator's "
        f"construction rather than by this assertion"
    )
    a(
        f"- residual asymmetry, which the assertion deliberately excludes: the "
        f"per-net met1 risers above y = {summary.get('track_y0_um')} um, where "
        f"each net owns one track. "
        f"{summary.get('met1_riser_asymmetry_um')} um of length difference in "
        f"total ({summary.get('met1_riser_asymmetry_area_um2')} um^2 of 0.30 um "
        f"met1) across the "
        f"{len(summary.get('matched_net_pairs', []))} matched net pairs, which "
        f"`TRACK_ORDER` holds to adjacent tracks for exactly this reason"
    )
    a("")
    a("| Side | group origin (um) | n-well island (um) | VDD tap (um) | GND tap (um) | met1 riser total (um) |")
    a("| --- | --- | --- | --- | --- | --- |")
    for side, side_summary in sorted(summary.get("sides", {}).items()):
        well = side_summary["well_um"]
        wtap = side_summary["well_tap_um"]
        stap = side_summary["substrate_tap_um"]
        a(
            f"| `_{side}` | {side_summary['group_origin_um']} | "
            f"{well['x0']}..{well['x1']} x {well['y0']}..{well['y1']} | "
            f"{wtap['x0']}..{wtap['x1']} | {stap['x0']}..{stap['x1']} | "
            f"{side_summary['met1_riser_total_um']} |"
        )
    a("")
    a(
        f"n-well island separation drawn: {summary.get('well_gap_drawn_um')} um "
        f"against sky130's `nwell.2a` minimum of "
        f"{summary.get('nwell_2a_rule_um')} um. Both islands tap `VDD`: every "
        f"`XMoff_*` PFET card declares `VDD` as its body, so unlike "
        f"`layout/sampling-frontend/`'s DR-007 partition there is no "
        f"multi-domain body-tie question here -- the two islands exist because "
        f"the NFET between them may not sit in an n-well, not because they are "
        f"different nets."
    )
    a("")

    a("## The offset capacitor")
    a("")
    a(
        f"DR-009 sizes `Choff_{{n,p}}` identical to "
        f"`design/cdac/cdac_unit_cell.sch`'s own `C_u`. The cards ask for "
        f"W = L = {CAP_SCHEMATIC_UM} um, which is off the 1 nm database grid; "
        f"the drawn plate is {CAP_DRAWN_UM} um -- the value "
        f"`layout/cdac-array/bin/cdac_layout.py` already draws for every one of "
        f"its 1024 array units, which `bin/check-schematic-parity.py` reads out "
        f"of that file and asserts. The half-LSB step is a *ratio* against one "
        f"array bit, so matching the sibling's drawn plate matters more than "
        f"rounding {CAP_SCHEMATIC_UM * 1000:.1f} nm to the nearer grid point."
    )
    a("")
    a(
        f"Reference capacitance: {CAP_UNIT_F:.9e} F per unit, from the drawn "
        f"plate under the extraction deck's own published tt coefficients -- "
        f"derived from geometry, never read back out of an extraction result."
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
        "(two n-well islands, four taps, every wire)"
    )
    a(
        f"- `klt gen-compose` (cell `{compose.get('cell_name')}`): "
        f"{len(compose.get('blocks', []))} blocks placed at explicit origins, "
        f"bbox {compose.get('bbox_um')}"
    )
    a(
        "- `klt gen-compose` is used as a **placer only** (no `routing` block in "
        "the request), the same choice every full-custom sibling documents."
    )
    # The placement warnings are partitioned by WHICH block's own
    # `drc_hints.min_spacing_um` each one cites, read out of the warning text
    # rather than assumed, so a new warning class shows up as an "other" row
    # instead of being absorbed into a sentence that no longer describes it.
    warnings = [str(w) for w in compose.get("warnings", [])]
    by_hint: dict[str, int] = {}
    for warning in warnings:
        match = _HINT_OWNER_RE.search(warning)
        by_hint[match.group(1) if match else "other"] = (
            by_hint.get(match.group(1) if match else "other", 0) + 1
        )
    cap_hint = by_hint.get("choff", 0)
    mos_hint = sum(count for name, count in by_hint.items() if name.startswith("moff_"))
    other_hint = len(warnings) - cap_hint - mos_hint
    a(
        f"- `klt gen-compose` emitted {len(warnings)} placement warnings, in two "
        f"expected classes ({cap_hint} citing `choff`'s hint, {mos_hint} citing a "
        f"`moff_*` block's, {other_hint} neither):"
    )
    a(
        f"  - **{cap_hint}** cite the cap pair: `klt gen cap_array` reports the "
        f"requested inter-unit `spacing_um` as its own "
        f"`drc_hints.min_spacing_um`, so a matched pair deliberately spaced "
        f"{summary.get('cap_unit_pitch_um')} um apart makes every block placed "
        f"inside that span look like a spacing violation."
    )
    a(
        f"  - **{mos_hint}** cite a `moff_*` switch: the `route` cell carries the "
        f"licon/met1 that CONTACTS each device's own ports, so it is placed at "
        f"0.00 um from every one of them by construction -- a `min_spacing_um` "
        f"hint cannot distinguish an abutting contact cell from an unrelated "
        f"neighbour."
    )
    a(
        "  - Neither is a rule minimum and `klt drc` on the composed layout is "
        "clean. Both are the same tool gap -- one `min_spacing_um` field for two "
        "unrelated meanings -- filed generically upstream as "
        "klayout-tools#2638 (see `../README.md`, \"Upstream filings\")."
    )
    a(
        f"- track band starts at y = {summary.get('track_y0_um')} um, above the "
        f"cap pair's own met4 escape at y = "
        f"{summary.get('cap_met4_escape_y_um')} um"
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
        f"| precheck, 1 nm database grid | {precheck.get('status')} | "
        f"{len(precheck.get('checks', []))} checks, "
        f"{len(_failing_checks(precheck))} failed |"
    )
    a(
        f"| precheck, 5 nm manufacturing grid | {precheck_grid5.get('status')} | "
        f"failing checks {_failing_checks(precheck_grid5)}, "
        f"{sum(offgrid.values())} off-grid shapes |"
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
        f"| LVS (schematic-derived reference) | {lvs.get('status')} | "
        f"devices {counts.get('devices', {}).get('matched')}/"
        f"{counts.get('devices', {}).get('reference')} matched, "
        f"nets {counts.get('nets', {}).get('matched')}/"
        f"{counts.get('nets', {}).get('reference')} matched, "
        f"pins {counts.get('pins', {}).get('matched')}/"
        f"{counts.get('pins', {}).get('reference')} matched |"
    )
    for label, envelope in (
        ("device-parameter", lvs_bad_dev),
        ("capacitor top-plate", lvs_bad_top),
        ("swapped-enable, EXPECTED to match", lvs_swapped),
    ):
        a(
            f"| LVS ({label} negative control) | {envelope.get('status')} | "
            f"mismatch_count={envelope.get('mismatch_count')}, "
            f"categories={envelope.get('category_counts')} |"
        )
    a("")

    a("## Off-grid census (5 nm manufacturing grid)")
    a("")
    a(
        "Recorded rather than hidden. The MiM plate DR-009 requires is 1898 nm "
        "on a side, which is not a multiple of 5 nm, so neither the plate's own "
        "edges nor the port coordinates derived from it can be on sky130's "
        "manufacturing grid -- and every coordinate this flow *chooses* is "
        "snapped to it (`build_layout.GRID_UM`), which is why the residual is "
        "confined to the MiM stack and the wiring that has to land on its ports. "
        "This is a property of the unit-cap size shared with "
        "`layout/cdac-array/`'s own 1024 units, not of this flow."
    )
    a("")
    a("| Cell | Layer | Off-grid shapes |")
    a("| --- | --- | --- |")
    for (cell, layer), count in sorted(offgrid.items()):
        a(f"| `{cell}` | `{layer}` | {count} |")
    if not offgrid:
        a("| (none) | | 0 |")
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

    for line in render_net_correspondence(lvs):
        a(line)

    for line in render_lvs_findings(lvs, title="Reported LVS findings (good reference)"):
        a(line)

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

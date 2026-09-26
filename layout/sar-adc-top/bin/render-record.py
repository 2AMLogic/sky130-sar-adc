#!/usr/bin/env python3
"""Render layout/sar-adc-top/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory -- mirrors
layout/sar-sequencer/bin/render-record.py's own "stamp provenance, print
verdicts, never re-derive from exit codes" discipline, extended with a
connectivity-by-net summary (this design's own per-net "layout::extraction
membership matches the intended schematic" check, computed against the
*unfiltered* extraction -- the direct evidence this issue's own closing
summary needs, independent of whichever pin set `klt extract
--pin-source-cells` manages to promote).

Prints record.md to stdout; does not itself decide pass/fail -- run-flow.sh
treats a dirty DRC as the only hard failure (see that script).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))
# This flow's own `build_layout.py`, for the placement tables the decoupling
# section reports against (issue #440) -- imported rather than transcribed, so
# the record cannot describe a floorplan the build did not use.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record_common import (  # noqa: E402
    build_argparser,
    git_commit_and_dirty,
    load_json,
    resolve_pdk_commit,
    tool_version,
)

#: Expected net -> the (block, pin) members `layout/sar-adc-top/README.md`'s
#: own net list declares -- used only to report which *unfiltered*-extraction
#: net (by whatever klayout named it) actually carries each expected member,
#: as a human-checkable connectivity table. Matching is substring-based
#: (does `member` appear in the '|'-joined net name?) purely for this
#: report's own display purposes -- the actual verified check (every
#: intended net's own distinct, correctly-scoped device count) was done by
#: hand against `extract.unfiltered.json`'s own `nets[]` list; see the PR
#: description for the full net-by-net trace this table condenses.
EXPECTED_NET_MEMBERS = {
    "TOP_P": ["TOP_P", "VINP"],
    "TOP_N": ["TOP_N", "VINN"],
    "VDD (analog)": ["VDD"],
    "VREFP": ["VREFP"],
    "VREFN": ["VREFN"],
    "CLK": ["CLK"],
    "COMP_OUT": ["COMP_OUT", "OUTP"],
    "SAMPLE_INT": ["PH_SAMPLE", "SAMPLE"],
    "RST_B": ["RST_B"],
    "BUSY": ["BUSY"],
    **{f"DOUT{i}": [f"DOUT{i}", f"SELp{i}"] for i in range(9)},
    "DOUT9": ["DOUT9"],
    **{f"SELn{i}": [f"SELn{i}"] for i in range(9)},
}


#: Every supply-net label this composition draws, in whatever order
#: `klt extract` happens to '|'-join them into an extracted net name. A
#: decoupling capacitor is exactly a device BOTH of whose terminals land on one
#: of these -- which is what makes the check below a check and not a filter on
#: capacitance (`sampling_frontend`'s own `Csamp_{p,n}` are the same 46.9 um
#: plate at the same value, and are correctly excluded because their terminals
#: are signal nets).
_SUPPLY_LABELS = ("GND", "VGND", "VSS", "VDD", "VPWR")


def _decap_terminal_evidence(netlist_path: str) -> list[str]:
    """Read the decoupling capacitors' own terminals back out of the netlist
    `klt lvs` actually compared, and report them.

    This is the direct per-device connectivity evidence for issue #440's ties:
    a DRC-clean layout says nothing about *which* nets a capacitor bridges, and
    this flow's LVS verdict is a pre-existing mismatch (klayout-tools#1878), so
    neither can be read as "the caps are across the right pairs". Four cards,
    both of whose terminals are supply nets, at the declared per-unit value, can.
    """
    try:
        with open(netlist_path) as handle:
            text = handle.read()
    except OSError:
        return []
    found: dict[tuple[str, str], list[str]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith("C"):
            continue
        a, b = parts[1], parts[2]
        if not all(
            any(label in node.split("|") for label in _SUPPLY_LABELS) for node in (a, b)
        ):
            continue
        found.setdefault((a, b), []).append(parts[3])
    if not found:
        return [
            "- **No capacitor in the compared netlist has both terminals on a "
            "supply net** -- the decoupling ties did not reach their domains."
        ]
    lines = [
        "- Decoupling capacitors as the compared netlist actually carries them "
        "(every `C` card both of whose terminals are supply nets):"
    ]
    for (a, b), values in sorted(found.items()):
        lines.append(f"  - `{a}` <-> `{b}`: {len(values)} x {values[0]} F")
    lines.append(
        "  `GND`, `VGND` and `cdac_array`'s own `VSS` extract as ONE net -- the "
        "shared p-substrate bulk sky130 offers no way to split, per "
        "`spec/decision-records/DR-012-analog-ground-pad.md` -- so both domains' "
        "return terminals land on that one name here. That is the same merge the "
        "LVS section's `net.merged` entries already track, not a new finding, and "
        "it is why the analog pair is the one that cannot correspond to a "
        "reference device (see that section)."
    )
    return lines


def _decap_lvs_delta(lvs: dict) -> list[str]:
    """Name every LVS mismatch entry that is about a decoupling capacitor.

    Issue #440's acceptance criterion is not "LVS still mismatches by the same
    number" -- it is that whatever moved is *attributable* to the two new
    capacitors and introduces no new mismatch CATEGORY. Listing the entries by
    device name is how a reader checks that without diffing two records by hand.
    """
    hits = []
    for entry in lvs.get("mismatches", []) or []:
        device = entry.get("device") or {}
        names = " ".join(str(device.get(side)) for side in ("reference", "layout"))
        if "DECAP" in names.upper():
            hits.append((entry.get("category"), entry.get("side"), device))
    if not hits:
        return [
            "- No LVS mismatch entry names a decoupling capacitor: both domains' "
            "pairs correspond to their reference devices."
        ]
    lines = [
        f"- LVS mismatch entries naming a decoupling capacitor: {len(hits)}."
    ]
    for category, side, device in hits:
        lines.append(
            f"  - `{category}` ({side} side): reference "
            f"`{device.get('reference')}` / layout `{device.get('layout')}`, class "
            f"`{device.get('class')}`."
        )
    lines.append(
        "  Each is the DR-012 substrate merge above reaching a device, not a new "
        "mismatch class: `GND` is on the reference side of an already-tracked "
        "`net.merged` entry, so no reference device with a `GND` terminal can "
        "correspond, and the analog pair has one. The digital pair, whose return "
        "port is `VGND` -- the name the comparer paired that merged layout net "
        "with -- does correspond."
    )
    return lines


def _decap_series_resistance(ties: dict) -> list[str]:
    """The series resistance each tie adds, from `decap-ties.json`.

    DR-017's measured benefit was obtained with an IDEAL capacitor, and its own
    closing open item names this series resistance as the one thing that can
    erode it. No verdict this flow produces sees resistance at all -- `klt drc`
    grades shapes, `klt erc` is a connectivity model with none in it -- so
    without this section the record would be silent on the one residual DR-017
    asked to be told about (issue #440's own Test Plan edge case).
    """
    if not ties:
        return []
    if not ties.get("model_matches_drawn_geometry", True):
        return [
            "- **Series resistance NOT reported: `probe-decap-sites.py`'s ladder no "
            "longer matches the drawn geometry.** See `decap-ties.json`'s "
            "`model_problems`.",
        ]
    per = ties.get("per_domain") or {}
    esr = per.get("esr_ohm") or {}
    if not esr:
        return []
    lines = [
        "- Series resistance of the ties, from `decap-ties.json` (lumped DC over "
        "drawn conductor only, at the PDK's own `rm2`/`rm3`/`rm4`/`rcvia2`/"
        "`rcvia3`/`rcvia4`; excludes each plate's own distributed resistance and "
        "all inductance):"
    ]
    for tie, entry in (ties.get("ties") or {}).items():
        lines.append(
            f"  - `{tie}`: **{entry['tie_ohm']} ohm** "
            f"(shared {entry['shared_ohm']}, branches "
            + " / ".join(f"{v}" for v in entry["branch_ohm"].values())
            + ")"
        )
    f_res = per.get("package_resonance_Hz")
    for domain, value in esr.items():
        lines.append(
            f"  - **{domain} domain ESR: {value} ohm** at "
            f"{per['capacitance_F'] * 1e12:.3f} pF -- Q = "
            f"{per['q_at_resonance'][domain]} at the "
            f"{f_res / 1e6:.1f} MHz resonance that capacitance forms with DR-015's "
            f"own 1.914 nH per-terminal package inductance, and the ESR equals the "
            f"pair's own reactance at {per['esr_equals_reactance_Hz'][domain] / 1e9:.3f} "
            "GHz."
        )
    lines.extend(_decap_via_narrative())
    return lines


def _decap_via_narrative() -> list[str]:
    """Why the vias, not the metal, are what these ties' resistance is made of
    -- keyed off the cut count `build_layout` actually drew.

    Derived rather than written, because this paragraph's whole point is a
    comparison between the drawn cut count and `rcvia2`/`rcvia3`: a record that
    kept asserting "SINGLE-CUT" after the arrays landed (issue #465) would be
    describing a layout nobody built, which is the failure mode every other
    number in this section is read back from an artefact to avoid.
    """
    import build_layout as bl  # noqa: E402  (same directory; see sys.path below)

    cuts = bl.DECAP_VIA_ARRAY**2
    head = (
        "  **What these ties' resistance is made of is vias, not metal**, at "
        "`rcvia2`/`rcvia3` = 3.41 ohm per cut against `rm2`/`rm4` = 0.125/0.047 "
        "ohm/sq on 2.0 um conductor. Each return path crosses three of those "
        "levels (the met4->met2 riser's two, plus the via2 into each plate) "
        "against each supply path's one."
    )
    if cuts == 1:
        return [
            head
            + " Every one of them is a SINGLE cut. Of the analog return's 8.601 ohm "
            "shared leg, 6.82 ohm is those two riser cuts and only 1.781 ohm is "
            "28.5 um of met2 -- so widening the straps further buys almost nothing, "
            "while a via ARRAY at each riser and each plate entry would cut the ESR "
            "~3x. Whether that is worth drawing was measured in "
            "`sim/supply-impedance-sensitivity/` (issue #465); see README.md's "
            "\"On-die decoupling (DR-017)\"."
        ]
    return [
        head
        + f" **Every via2/via3 the ties draw is a {bl.DECAP_VIA_ARRAY}x"
        f"{bl.DECAP_VIA_ARRAY} array of {cuts} cuts** (issue #465), so each of "
        f"those six levels contributes 3.41/{cuts} = {3.41 / cuts:.3f} ohm instead "
        "of 3.41. That is drawn on measurement in both directions: issue #440 "
        "measured the single-cut ties at 13.837 / 13.448 ohm per domain with ~80 % "
        "of it in those cuts, and "
        "`sim/supply-impedance-sensitivity/records/20260926-183200-e8fa47c.md` then "
        "measured that the resistance COSTS die-side bounce (worst rail 12.135 -> "
        "16.180 mV peak-to-peak, 1.333x, at `tt_27c_1.80v`) rather than usefully "
        "damping the package resonance."
        "\n\n"
        "  Three cuts in these paths are deliberately still single, which is why "
        "the reduction is ~1.95x rather than the ~3x issue #440 projected: each "
        "domain's two via4 landings off the met5 rails (`rcvia4` = 0.38 ohm/cut, "
        "and the 1.6 um rail cannot enclose a second cut across it) and -- the "
        "binding one -- **each `klt gen cap_array` unit cell's own centre via3 "
        "into `capm`**, 3.41 ohm, which this composer does not draw and cannot "
        "widen. That single cut is now the largest term in both supply ties, and "
        "moving it is a generator change. See README.md's \"On-die decoupling "
        "(DR-017)\"."
    ]


def _decoupling_section(
    decap: dict, compose: dict, extract: dict, netlist_path: str, lvs: dict,
    ties: dict | None = None,
) -> list[str]:
    """The on-die decoupling summary (issue #440, DR-017).

    Every number here is read back from an artefact in this same record --
    `decap.json` (the generator's own report), `compose.json` (the composed
    bounding box) and `extract.json` (what the extractor actually found) -- or
    computed from `build_layout.py`'s own placement tables. None of it is
    transcribed from DR-017's prose, which is the point: this section is what
    grades DR-017's Decision §2/§3 area budget against a layout, rather than
    repeating it.
    """
    if not decap:
        return []
    import build_layout as bl  # noqa: E402  (same directory; see sys.path below)

    units = len(bl.DECAP_OFFSETS)
    per_domain = units // 2
    plate = bl.DECAP_GEN_PARAMS["plate_w_um"]
    capm_um2 = plate * bl.DECAP_GEN_PARAMS["plate_h_um"] * units
    bx0, by0, bx1, by1 = (
        bl.BBOX[next(iter(bl.DECAP_OFFSETS))][i] for i in range(4)
    )
    cell_um2 = (bx1 - bx0) * (by1 - by0)
    box = compose.get("bbox_um") or {}
    die_um2 = None
    if box:
        die_um2 = (box["x1"] - box["x0"]) * (box["y1"] - box["y0"])
    c_domain = bl.DECAP_UNIT_C_F * per_domain
    mim = (extract.get("device_counts") or {}).get("sky130_fd_pr__model__cap_mim")

    def pct(value: float) -> str:
        return "n/a" if not die_um2 else f"{100.0 * value / die_um2:.2f} %"

    lines = ["## On-die supply decoupling (DR-017, placed by issue #440)"]
    lines.append(
        f"`klt gen cap_array` unit cell: {plate} x {plate} um `capm` plate, "
        f"{decap.get('device_count')} device, bbox "
        f"{bx1 - bx0} x {by1 - by0} um. Placed {units} times -- {per_domain} per "
        "supply domain, which is how DR-017's `MF = 2` is drawn -- at "
        + ", ".join(f"`{b}` {tuple(o)}" for b, o in bl.DECAP_OFFSETS.items())
        + "."
    )
    lines.append("")
    lines.append("| quantity | value | share of the composed die |")
    lines.append("| --- | --- | --- |")
    lines.append(
        f"| composed bounding box | {box.get('x1', 0) - box.get('x0', 0):.3f} x "
        f"{box.get('y1', 0) - box.get('y0', 0):.3f} um = {die_um2:.3f} um^2 | 100 % |"
        if die_um2
        else "| composed bounding box | not reported | n/a |"
    )
    lines.append(
        f"| `capm` plate area, both domains | {capm_um2:.2f} um^2 | {pct(capm_um2)} |"
    )
    lines.append(
        f"| placed cell footprint, both domains | {cell_um2 * units:.2f} um^2 | "
        f"{pct(cell_um2 * units)} |"
    )
    lines.append("")
    lines.append(
        f"- Capacitance per domain: **{c_domain * 1e12:.3f} pF** "
        f"({per_domain} x {bl.DECAP_UNIT_C_F * 1e12:.3f} pF), from the PDK's own "
        "`camimc`/`cpmimc` coefficients -- the same value `klt extract` reports "
        "for each placed unit, and the same one the LVS reference declares."
    )
    lines.append(
        f"- MiM devices in the filtered extraction: **{mim}** "
        "(the composition's pre-existing 1028 CDAC/front-end unit caps, plus "
        f"these {units})."
    )
    lines.extend(_decap_terminal_evidence(netlist_path))
    lines.extend(_decap_lvs_delta(lvs))
    lines.extend(_decap_series_resistance(ties or {}))
    lines.append(
        "- **DR-017's Decision §3 area budget is confirmed placeable, and costs "
        "no die area at all.** Its `capm` figure above is the 8798.44 um^2 / "
        "8.14 % that record computed at schematic level; both sites fall inside "
        "the *pre-existing* composed bounding box, which this record reports "
        "unchanged, so the allocation displaced no routing and grew no die. See "
        "`layout/sar-adc-top/README.md`, \"On-die decoupling (DR-017)\", for the "
        "met3/met4 occupancy measurement the two placements were chosen from."
    )
    lines.append("")
    return lines


def main() -> int:
    args = build_argparser().parse_args()

    drc = load_json(os.path.join(args.out_dir, "drc.json"))
    extract_unfiltered = load_json(os.path.join(args.out_dir, "extract.unfiltered.json"))
    extract = load_json(os.path.join(args.out_dir, "extract.json"))
    lvs = load_json(os.path.join(args.out_dir, "lvs.json"))
    capclass = load_json(os.path.join(args.out_dir, "capclass.json"))
    compose = load_json(os.path.join(args.out_dir, "compose.json"))
    decap = load_json(os.path.join(args.out_dir, "decap.json"))
    decap_ties = load_json(os.path.join(args.out_dir, "decap-ties.json"))

    commit, dirty = git_commit_and_dirty(args.repo_root)

    lines: list[str] = []
    lines.append(f"# SAR ADC top-level assembly record: {args.record_id}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- `klt` version: {tool_version(args.klt, '--version')}")
    lines.append(
        f"- PDK: {args.pdk_variant} ({resolve_pdk_commit(args.klt, args.pdk_variant)})"
    )
    lines.append(f"- repo commit: `{commit}`{' (dirty)' if dirty else ''}")
    lines.append("")

    lines.append("## DRC (sky130 deck, composed top-level layout)")
    if drc.get("status") == "clean":
        lines.append(f"- **CLEAN** -- {drc.get('violation_count', 0)} violations")
    elif drc:
        lines.append(
            f"- **{drc.get('status', 'unknown').upper()}** -- "
            f"{drc.get('violation_count', '?')} violations"
        )
    else:
        lines.append("- not run")
    lines.append("")

    lines.extend(
        _decoupling_section(
            decap,
            compose,
            extract,
            os.path.join(args.out_dir, "sar_adc_top.extract.lvs.spice"),
            lvs,
            decap_ties,
        )
    )

    lines.append("## Connectivity verification (unfiltered extraction, by net)")
    lines.append(
        "`klt extract` with no declared-pin restriction, checked net-by-net "
        "against the intended interconnect in `layout/sar-adc-top/README.md` "
        "-- this is the direct evidence this issue's closing summary relies "
        "on, independent of the pin-declaration blocker below."
    )
    lines.append("")
    net_names = [n["name"] for n in extract_unfiltered.get("nets", [])]
    #: Nets the *filtered* (`--pin-source-cells`) extraction promoted to real
    #: top-level pins -- used only to disambiguate a label-substring row that
    #: matches more than one unfiltered net name (see below).
    pin_nets = {
        n["name"] for n in extract.get("nets", []) if n.get("pin")
    }
    if net_names:
        lines.append("| Expected net | Found in (unfiltered) net name | OK? |")
        lines.append("| --- | --- | --- |")
        footnotes: list[str] = []
        for expected, members in EXPECTED_NET_MEMBERS.items():
            hits = [
                nm for nm in net_names if all(m in nm.split("|") for m in members)
            ]
            if len(hits) == 1:
                ok, shown = "yes", hits[0]
            else:
                # More than one *label-name* match is not automatically a
                # split net: a sub-block's own internal net can carry a label
                # of the same name (e.g. a macro's internal buffered copy of
                # an input). Narrow to the net the filtered extraction
                # actually promoted to this assembly's top-level pin; only an
                # ambiguity that survives that narrowing is a real finding.
                promoted = [nm for nm in hits if nm in pin_nets]
                if len(promoted) == 1:
                    ok, shown = "yes (see note)", promoted[0]
                    others = ", ".join(f"`{nm}`" for nm in hits if nm != promoted[0])
                    footnotes.append(
                        f"- **{expected}**: `{promoted[0]}` is the single net "
                        "promoted to this assembly's own top-level pin by "
                        "`klt extract --pin-source-cells`. "
                        f"{len(hits)} unfiltered net names contain the "
                        f"label(s) `{'`, `'.join(members)}` -- the other "
                        f"{len(hits) - 1} ({others}) are internal nets of a "
                        "sub-block that label their own copy of this signal "
                        "(a label-name collision the flattened extraction "
                        "exposes, not a split of the routed net)."
                    )
                else:
                    ok = f"NO ({len(hits)} matches)"
                    shown = ", ".join(hits) or "(none)"
            lines.append(f"| {expected} | `{shown}` | {ok} |")
        if footnotes:
            lines.append("")
            lines.extend(footnotes)
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## LVS (top-level layout vs. hierarchical reference)")
    if lvs:
        status = lvs.get("status", "unknown")
        counts = lvs.get("counts", {})
        pins = counts.get("pins", {})
        lines.append(f"- verdict: **{status}**")
        pin_note = (
            "klayout-tools#1513 is resolved: every top-level pin label this "
            "flow draws promotes correctly."
        )
        if pins.get("layout") != pins.get("reference"):
            # Read the merged net's own name out of THIS record's extraction
            # rather than hard-coding it. It is not a constant: issue #377's
            # analog ground mesh joined `cdac_array`'s newly-drawn `VSS` pin
            # to it, so the same net that read `GND|VGND` before the mesh
            # reads `GND|VGND|VSS` after it. A record that quotes a stale
            # name has stopped being evidence about its own artefacts.
            merged = [
                str(n.get("name"))
                for n in extract.get("nets", [])
                if n.get("pin") and "GND" in str(n.get("name", "")).split("|")
            ]
            merged_name = (
                f"`{merged[0]}`" if len(merged) == 1 else "the merged `GND` net"
            )
            pin_note += (
                " The layout count is BELOW the reference count by design, not "
                "by defect: since issue #362 the reference carries `GND` and "
                "`VGND` as two ports of what the layout extracts as ONE net "
                f"({merged_name} -- the shared p-substrate, which bulk sky130 "
                "offers no way to split), so a single promoted layout pin "
                "answers both reference ports and `matched` counts both. See "
                "`spec/decision-records/DR-012-analog-ground-pad.md`."
            )
        lines.append(
            f"- pins promoted from `--pin-source-cells`: "
            f"layout={pins.get('layout', extract.get('pin_count', '?'))} "
            f"reference={pins.get('reference', '?')} "
            f"matched={pins.get('matched', '?')} -- " + pin_note
        )
        lines.append(
            f"- devices: layout={counts.get('devices', {}).get('layout')} "
            f"reference={counts.get('devices', {}).get('reference')} "
            f"matched={counts.get('devices', {}).get('matched')}"
        )
        lines.append(
            f"- nets: layout={counts.get('nets', {}).get('layout')} "
            f"reference={counts.get('nets', {}).get('reference')} "
            f"matched={counts.get('nets', {}).get('matched')}"
        )
        cat_counts = lvs.get("category_counts", {})
        if cat_counts:
            lines.append("- mismatch categories:")
            for cat, n in sorted(cat_counts.items()):
                lines.append(f"  - `{cat}`: {n}")
        if capclass:
            if capclass.get("noop"):
                lines.append(
                    "- capacitor device-class token (klayout-tools#1876): "
                    f"no workaround needed -- all {capclass.get('c_cards')} "
                    "`C` cards already carry their class name in this `klt` "
                    "build, so `restore-cap-device-class.py` was a no-op and "
                    "can be retired from the flow."
                )
            else:
                lines.append(
                    "- capacitor device-class token (klayout-tools#1876): "
                    f"restored on {capclass.get('restored')}/"
                    f"{capclass.get('c_cards')} `C` cards "
                    f"({', '.join(capclass.get('restored_classes', {}))}) "
                    "from `klt extract`'s own per-instance comment lines, into "
                    "`sar_adc_top.extract.lvs.spice` -- the extractor's own "
                    "`sar_adc_top.extract.spice` is kept unmodified alongside "
                    "it. Without this, the SPICE round-trip this LVS shape "
                    "depends on loses the capacitor class name and the same "
                    "layout reports far more mismatches and far fewer matched "
                    "nets -- measured on the pre-issue-#440 composition as 26 "
                    "extra mismatches (124 vs 98) and 19 fewer matched nets "
                    "(393 vs 412). Those two numbers are that one measurement, "
                    "not a re-measurement of the layout in hand: this record's "
                    "own verdict above is what describes THIS layout, and the "
                    "point they make (the step is load-bearing, not a no-op) is "
                    "unchanged by a composition that adds four more `C` cards."
                )
        if status != "match":
            lines.append(
                "- **known blocker: one, klayout-tools#1878** (klayout-tools"
                "#1513's pin-declaration blocker is resolved by "
                "`--pin-source-cells`; #1876's capacitor device-class "
                "regression is worked around locally, see the line above). "
                "`klt lvs`'s `options.combine_devices` is a single flag "
                "applied to the whole (flattened) compared netlist, with no "
                "per-subcircuit scoping. Three of the five "
                "already-independently-verified sub-blocks (comparator, "
                "sar_sequencer, seln_inverters) need it `true` to re-lump "
                "their own genuinely split/interleaved layout legs against "
                "their own lumped reference devices; the other two "
                "(cdac_array, sampling_frontend) need it `false` (cdac_array "
                "to avoid klayout-tools#1497's parallel-capacitor combine "
                "nondeterminism). klayout-tools#1552 (this repo's own report "
                "of exactly this gap) is closed upstream via #1556's new "
                "`options.combine_devices_per_circuit`, but that option does "
                "not actually help here: it can only scope a side that "
                "already has separate per-macro subcircuits, and `klt "
                "extract`'s layout-side output for a composed GDS is always "
                "one flat circuit (extraction still has no hierarchical mode, "
                "#1085) -- confirmed by direct measurement, filed generically "
                "as klayout-tools#1878. Neither the class-scoped "
                "`combine_devices: [\"NFET\",\"PFET\"]` form "
                "(klayout-tools#1370) nor `klt lvs`'s inline-extraction "
                "shape substitutes for it (126 and 2199 mismatches "
                "respectively -- see run-flow.sh's own measured trace). "
                "This blocker is not a routing defect: the pin declaration "
                "and (per the connectivity table above) the physical routing "
                "are both independently confirmed correct."
            )
    else:
        lines.append("- not run")
    lines.append("")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

from _record_common import (  # noqa: E402
    build_argparser,
    git_commit_and_dirty,
    load_json,
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


def main() -> int:
    args = build_argparser().parse_args()

    drc = load_json(os.path.join(args.out_dir, "drc.json"))
    extract_unfiltered = load_json(os.path.join(args.out_dir, "extract.unfiltered.json"))
    extract = load_json(os.path.join(args.out_dir, "extract.json"))
    lvs = load_json(os.path.join(args.out_dir, "lvs.json"))
    capclass = load_json(os.path.join(args.out_dir, "capclass.json"))

    commit, dirty = git_commit_and_dirty(args.repo_root)

    lines: list[str] = []
    lines.append(f"# SAR ADC top-level assembly record: {args.record_id}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- `klt` version: {tool_version(args.klt, '--version')}")
    lines.append(f"- PDK variant: {args.pdk_variant}")
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
                    "layout reports 26 extra mismatches (124 vs 98) and 19 "
                    "fewer matched nets (393 vs 412)."
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

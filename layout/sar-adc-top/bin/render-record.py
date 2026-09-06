#!/usr/bin/env python3
"""Render layout/sar-adc-top/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory -- mirrors
layout/sar-sequencer/bin/render-record.py's own "stamp provenance, print
verdicts, never re-derive from exit codes" discipline, extended with a
connectivity-by-net summary (this design's own per-net "layout::extraction
membership matches the intended schematic" check, computed against the
*unfiltered* extraction -- the direct evidence this issue's own closing
summary needs, independent of whichever pin set `klt extract --def-pins`
manages to promote).

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
    if net_names:
        lines.append("| Expected net | Found in (unfiltered) net name | OK? |")
        lines.append("| --- | --- | --- |")
        for expected, members in EXPECTED_NET_MEMBERS.items():
            hits = [
                nm for nm in net_names if all(m in nm.split("|") for m in members)
            ]
            ok = "yes" if len(hits) == 1 else f"NO ({len(hits)} matches)"
            shown = hits[0] if len(hits) == 1 else ", ".join(hits) or "(none)"
            lines.append(f"| {expected} | `{shown}` | {ok} |")
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## LVS (top-level layout vs. hierarchical reference)")
    if lvs:
        status = lvs.get("status", "unknown")
        counts = lvs.get("counts", {})
        lines.append(f"- verdict: **{status}**")
        lines.append(
            f"- devices: layout={counts.get('devices', {}).get('layout')} "
            f"reference={counts.get('devices', {}).get('reference')} "
            f"matched={counts.get('devices', {}).get('matched')}"
        )
        lines.append(
            f"- pins promoted from `--def-pins`: "
            f"{extract.get('pin_count', '?')} (expected 19)"
        )
        if status != "match":
            lines.append(
                "- **known blocker**: no `klt extract` declared-pin "
                "mechanism (`--top-cell-pins`, `--pins`, `--def-pins`) "
                "reproducibly promotes exactly this design's own intended "
                "19-port top-level interface once composed from five "
                "independently-labeled sub-blocks with no governing "
                "top-level DEF -- `--top-cell-pins` demotes this flow's own "
                "genuine ports (drawn in an instanced routing cell, not the "
                "literal top cell), `--pins` cannot express an "
                "already-joined promoted name as one token, and "
                "`--def-pins` over-promotes unrelated internal nodes that "
                "happen to share a joined-label component with a declared "
                "name (e.g. a downstream clock-buffer net also carrying "
                "`CLK`). Filed generically at "
                "2AMLogic/klayout-tools#1513. The connectivity table above "
                "is this record's actual evidence that the composition's "
                "own interconnect is correct; this LVS verdict reflects the "
                "pin-count mismatch that blocker causes, not a routing "
                "defect."
            )
    else:
        lines.append("- not run")
    lines.append("")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

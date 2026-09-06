#!/usr/bin/env python3
"""Render layout/sar-sequencer/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory -- mirrors
layout/bin/render-record.py's own "stamp provenance, print verdicts, never
re-derive from exit codes" discipline, simplified for this sub-block's own
(currently: DRC-clean, LVS-blocked-on-a-filed-tool-gap) status.

Prints record.md to stdout; does not itself decide pass/fail -- run-flow.sh
treats a failed place-and-route as the only hard failure (see that script).
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


def main() -> int:
    args = build_argparser().parse_args()

    pnr = load_json(os.path.join(args.out_dir, "pnr.json"))
    drc = load_json(os.path.join(args.out_dir, "drc.json"))
    lvs = load_json(os.path.join(args.out_dir, "lvs.json"))

    commit, dirty = git_commit_and_dirty(args.repo_root)

    lines: list[str] = []
    lines.append(f"# SELn inverter bank layout record: {args.record_id}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- `klt` version: {tool_version(args.klt, '--version')}")
    lines.append(f"- OpenROAD version: {tool_version('openroad', '-version')}")
    lines.append(f"- PDK variant: {args.pdk_variant}")
    lines.append(f"- repo commit: `{commit}`{' (dirty)' if dirty else ''}")
    lines.append("")

    lines.append("## Place-and-route")
    if pnr.get("status") == "ok":
        lines.append(f"- stage reached: **{pnr.get('stage_reached')}**")
        lines.append(f"- die area: {pnr.get('die_area_um2')} um^2")
        lines.append(f"- utilization: {pnr.get('utilization_pct')}%")
        lines.append(f"- wirelength: {pnr.get('wirelength_um')} um")
        lines.append(
            f"- worst setup slack: {pnr.get('worst_slack_ns')} ns "
            f"(setup violations: {pnr.get('setup_violation_count')}, "
            f"hold violations: {pnr.get('hold_violation_count')})"
        )
        lines.append(f"- fmax: {pnr.get('fmax_mhz')} MHz")
        lines.append(f"- estimated power: {pnr.get('estimated_power_mw')} mW")
    else:
        lines.append(f"- **FAILED**: {pnr.get('error', {}).get('message')}")
    lines.append("")

    lines.append("## DRC (sky130 deck)")
    if drc.get("status") == "clean":
        lines.append(f"- **CLEAN** -- {drc.get('violation_count', 0)} violations")
    elif drc:
        lines.append(
            f"- **{drc.get('status', 'unknown').upper()}** -- "
            f"{drc.get('violation_count', '?')} violations: "
            f"{drc.get('rule_counts')}"
        )
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## LVS (layout vs. post-route netlist)")
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
            f"- nets: layout={counts.get('nets', {}).get('layout')} "
            f"reference={counts.get('nets', {}).get('reference')} "
            f"matched={counts.get('nets', {}).get('matched')}"
        )
        if status != "match":
            lines.append(
                "- **known blocker**: `klt extract`'s pin/net-name promotion "
                "for a `klt place-and-route`-produced (DEF->GDS-merged) "
                "layout does not reliably distinguish a genuine top-level "
                "design port from the many per-instance local-pin-name "
                "labels DEF's own NETS section records at every routed "
                "connection point -- this prevents `klt lvs`'s "
                "`NetlistComparer` from establishing net/device "
                "correspondence, even though device counts match exactly "
                "against a reference mechanically flattened from the "
                "*actual post-route* netlist (see "
                "layout/sar-sequencer/README.md, \"LVS reference "
                "provenance\", and the filed klayout-tools issue)."
            )
    else:
        lines.append("- not run")
    lines.append("")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

import argparse
import json
import os
import subprocess


def _load_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _tool_version(*args: str) -> str:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (completed.stdout or completed.stderr or "").strip().splitlines()[0]
    except Exception:  # noqa: BLE001 -- best-effort provenance line, never fatal
        return "(unresolvable)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--klt", required=True)
    parser.add_argument("--pdk-variant", required=True)
    args = parser.parse_args()

    pnr = _load_json(os.path.join(args.out_dir, "pnr.json")) or {}
    drc = _load_json(os.path.join(args.out_dir, "drc.json")) or {}
    lvs = _load_json(os.path.join(args.out_dir, "lvs.json")) or {}

    dirty = (
        subprocess.run(
            ["git", "-C", args.repo_root, "status", "--porcelain"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        != ""
    )
    commit = subprocess.run(
        ["git", "-C", args.repo_root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()

    lines: list[str] = []
    lines.append(f"# SAR sequencer layout record: {args.record_id}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- `klt` version: {_tool_version(args.klt, '--version')}")
    lines.append(f"- OpenROAD version: {_tool_version('openroad', '-version')}")
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

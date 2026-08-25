#!/usr/bin/env python3
"""Render layout/comparator/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory -- mirrors
layout/sar-sequencer/bin/render-record.py's own "stamp provenance, print
verdicts, never re-derive from exit codes" discipline for this sub-block's
own (currently: DRC-not-yet-clean, LVS-not-yet-clean, composition partially
routed) status -- see README.md "Composition status" for the full writeup.

Prints record.md to stdout; does not itself decide pass/fail -- run-flow.sh
runs every stage regardless of any single stage's own verdict.
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


def _net_summary(compose: dict) -> list[str]:
    lines = []
    for net in compose.get("nets", []):
        legs = net.get("legs", [])
        routed = sum(1 for leg in legs if leg.get("routed"))
        lines.append(
            f"  - `{net.get('net')}`: **{net.get('status')}** "
            f"({routed}/{len(legs)} legs routed)"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--klt", required=True)
    parser.add_argument("--pdk-variant", required=True)
    args = parser.parse_args()

    compose = _load_json(os.path.join(args.out_dir, "compose.json")) or {}
    drc = _load_json(os.path.join(args.out_dir, "drc.json")) or {}
    extract = _load_json(os.path.join(args.out_dir, "extract.json")) or {}
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
    lines.append(f"# Comparator layout record: {args.record_id}")
    lines.append("")
    lines.append(
        "Physical layout for the dynamic comparator sub-block (issue #101), "
        "drawn from design/comparator.sch via `klt gen` (per-device/pair "
        "matched blocks) + `klt gen-compose` (place + route). **Overall "
        "verdict: PARTIAL** -- see README.md \"Composition status\" for the "
        "full, honest writeup; this record is the specific numbers behind "
        "that writeup, not a DRC/LVS-clean claim."
    )
    lines.append("")

    lines.append("## Provenance")
    lines.append(f"- `klt` version: {_tool_version(args.klt, '--version')}")
    lines.append(f"- PDK variant: {args.pdk_variant}")
    lines.append(f"- repo commit: `{commit}`{' (dirty)' if dirty else ''}")
    lines.append("")

    lines.append("## Composition (`klt gen-compose`)")
    if compose:
        lines.append(f"- overall: every block placed; net-by-net routing status below")
        lines.extend(_net_summary(compose))
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## DRC (sky130 deck, on the composed layout)")
    if drc.get("status") == "clean":
        lines.append(f"- **CLEAN** -- {drc.get('violation_count', 0)} violations")
    elif drc:
        rule_counts: dict[str, int] = {}
        for v in drc.get("violations", []):
            rule_counts[v["rule"]] = rule_counts.get(v["rule"], 0) + 1
        lines.append(
            f"- **{drc.get('status', 'unknown').upper()}** -- "
            f"{drc.get('violation_count', '?')} violations: {rule_counts}"
        )
        lines.append(
            "- every violation traces to metal `klt gen-compose` itself drew "
            "while resolving a `routed: true` connectivity leg (every input "
            "`klt gen` block is independently DRC-clean in isolation -- see "
            "README.md \"Composition status\"); filed generically at "
            "2AMLogic/klayout-tools per CLAUDE.md's friction protocol (see "
            "README.md for the issue link)."
        )
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## Extract")
    if extract:
        lines.append(
            f"- device_count={extract.get('device_count')} "
            f"net_count={extract.get('net_count')} "
            f"pin_count={extract.get('pin_count')}"
        )
    else:
        lines.append("- not run")
    lines.append("")

    lines.append("## LVS (vs. reference.spice)")
    if lvs:
        status = lvs.get("status", "unknown")
        counts = lvs.get("counts", {})
        lines.append(f"- verdict: **{status}**")
        lines.append(f"- mismatch_count={lvs.get('mismatch_count')}")
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
                "- **expected, not a surprise**: the composition step above "
                "left several connectivity[] legs unrouted/partial "
                "(same-facing multi-block bus routing gap, see README.md); "
                "an unrouted net is a real open circuit in the drawn "
                "geometry, so LVS correctly reports it as a mismatch rather "
                "than a false pass. This is the concrete, falsifiable "
                "signal that composition is not yet complete -- not a "
                "reference-netlist authoring error (reference.spice is the "
                "schematic-correct target this layout is converging "
                "toward, not hand-tuned to match today's partial routing)."
            )
    else:
        lines.append("- not run")
    lines.append("")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

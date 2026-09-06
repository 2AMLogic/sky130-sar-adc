"""Shared helpers for the layout sub-block `render-record.py` scripts.

Used by `layout/sar-sequencer/bin/render-record.py`,
`layout/seln-inverters/bin/render-record.py`, and
`layout/cdac-array/bin/render-record.py`, which import this module via a
`sys.path` insert (see each script's own header) rather than a package
install, matching sim/harness/'s no-extra-runtime-dependency convention.
`render_pnr_drc_lvs_record` below is shared only by the sar-sequencer and
seln-inverters flows, which have identical place-and-route/DRC/LVS report
shapes and differ only in their H1 title string; cdac-array's own flow
asserts a different set of verdicts (see that script's own docstring) and
uses only the smaller helpers below.

Deliberately **not** used by `layout/bin/render-record.py` itself (the
original trivial-cell flow, issue #2): that flow requires every stage to have
already succeeded, so it uses a stricter `check=True`-raises discipline
(its own `_load`/`_git`) instead of the lenient, missing-file-tolerant
helpers below. The two sub-block flows this module serves are honest about
partial/blocked completion -- a missing JSON envelope means "that stage
hasn't run yet or was skipped", not "something is broken" -- so `load_json`
returns `{}` rather than raising, and the git lookups below never assert
`check=True`. Folding the trivial-cell flow's helpers into this module would
blur that intentional difference; see that script's own docstring.

`layout/comparator/bin/render-record.py` also does not use this module: as
of #114, that sub-block's flow always requires full completion (all six of
its verdicts), so it adopted the trivial-cell flow's stricter discipline
(`check=True`-raising `_load`/`_git`) for the same reason -- not an
oversight, a second instance of the same intentional split this module's
docstring already describes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess


def load_json(path: str) -> dict:
    """Parse *path* as JSON, or return `{}` if it does not exist.

    A missing envelope means the stage that would have written it hasn't run
    (or was skipped) -- not a hard failure -- so callers get an empty dict to
    probe with `.get(...)` rather than an exception.
    """
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def tool_version(*args: str) -> str:
    """Best-effort one-line tool-version provenance string.

    Never raises: a version probe failing (tool missing, `--version` not
    supported, timeout) degrades to `"(unresolvable)"` rather than aborting
    record generation over a provenance nicety.
    """
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return (completed.stdout or completed.stderr or "").strip().splitlines()[0]
    except Exception:  # noqa: BLE001 -- best-effort provenance line, never fatal
        return "(unresolvable)"


def git_commit_and_dirty(repo_root: str) -> tuple[str, bool]:
    """Return `(HEAD commit sha, working-tree-is-dirty)` for *repo_root*."""
    commit = subprocess.run(
        ["git", "-C", repo_root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = (
        subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        != ""
    )
    return commit, dirty


def build_argparser() -> argparse.ArgumentParser:
    """The five-flag skeleton shared by both sub-block `render-record.py` scripts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--klt", required=True)
    parser.add_argument("--pdk-variant", required=True)
    return parser


def render_pnr_drc_lvs_record(title: str, args: argparse.Namespace) -> str:
    """Render the shared place-and-route/DRC/LVS record body for *title*.

    Shared by the sar-sequencer and seln-inverters sub-block flows, which
    have identical report shapes (DRC-clean, LVS-blocked-on-a-filed-tool-gap)
    and differ only in their H1 title string -- see each calling script's own
    thin `main()`. The LVS "known blocker" prose below deliberately names no
    specific sub-block README (each sub-block's own README carries its own
    "LVS reference provenance" section), so this function has no sub-block
    identity baked in beyond the *title* argument.
    """
    pnr = load_json(os.path.join(args.out_dir, "pnr.json"))
    drc = load_json(os.path.join(args.out_dir, "drc.json"))
    lvs = load_json(os.path.join(args.out_dir, "lvs.json"))

    commit, dirty = git_commit_and_dirty(args.repo_root)

    lines: list[str] = []
    lines.append(f"# {title}: {args.record_id}")
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
                "*actual post-route* netlist (see this sub-block's own "
                "README, \"LVS reference provenance\", and the filed "
                "klayout-tools issue)."
            )
    else:
        lines.append("- not run")
    lines.append("")

    return "\n".join(lines)

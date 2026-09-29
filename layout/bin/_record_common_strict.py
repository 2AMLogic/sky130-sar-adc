"""Shared "strict discipline" helpers for the layout `render-record.py`
scripts that require every stage to have already completed before rendering
runs.

Used by `layout/bin/render-record.py` (trivial-cell), `layout/comparator/bin/
render-record.py`, `layout/sampling-frontend/bin/render-record.py`, and
`layout/sampling-frontend-wells/bin/render-record.py` -- each imports this
module via a `sys.path` insert (see any of the four scripts' own header)
rather than a package install, matching sim/harness/'s
no-extra-runtime-dependency convention.

Deliberately a **separate** module from `layout/bin/_record_common.py`, not a
merge into it. That module's docstring documents an intentional split: its
`load_json`/git helpers are lenient and missing-file-tolerant, for flows
(`layout/cdac-array/`, `layout/sar-sequencer/`) that are honest about
partial/blocked completion, where a missing JSON envelope means "that stage
hasn't run yet" rather than "something is broken". The four flows this
module serves are the opposite: they require full completion, so a missing or
malformed envelope should raise rather than degrade to `{}`. Folding either
flavor into the other would blur that intentional difference -- see
`_record_common.py`'s own docstring for the fuller rationale. The
`tool_version_strict`/`resolve_pdk_info_strict` pair below is this module's
own strict analogue of that module's best-effort
`tool_version`/`resolve_pdk_commit` pair, for the same reason.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def load_json_strict(path: Path) -> dict:
    """Parse *path* as JSON, raising `FileNotFoundError`/`JSONDecodeError` if
    it is missing or malformed.

    Every stage that would write *path* is assumed to have already run to
    completion; callers that need lenient, missing-file-tolerant loading
    should use `_record_common.load_json` instead.
    """
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def git_field(repo_root: Path, *args: str) -> str:
    """Run `git -C <repo_root> <*args>`, raising on a nonzero exit, and
    return its stripped stdout."""
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def tool_version_strict(*args: str) -> str:
    """Run `<*args>` (e.g. `klt --version`), raising on a nonzero exit, and
    return its stripped stdout as a one-line provenance string.

    The strict counterpart of `_record_common.tool_version`, which degrades a
    failed probe to `"(unresolvable)"`. A flow using this module has already
    run every stage to completion against some tool install; if that install
    can no longer be interrogated, the record cannot honestly name what
    produced it, so rendering aborts rather than stamping a placeholder.

    `[*args]` rather than `args`: a `CalledProcessError` renders the argv it
    was handed verbatim, so passing a list keeps the failure message
    character-identical to the inlined `subprocess.run([...])` calls this
    helper replaced.
    """
    return subprocess.run(
        [*args], check=True, capture_output=True, text=True
    ).stdout.strip()


def resolve_pdk_info_strict(klt: str, pdk_variant: str) -> dict:
    """Return the parsed `klt pdk find --pdk <pdk_variant> --format json`
    envelope, raising on a nonzero exit or malformed JSON.

    The strict counterpart of `_record_common.resolve_pdk_commit`, which
    returns only the resolved `open_pdks` commit and degrades to
    `"(unresolvable)"`. The flows using this module print several of the
    envelope's fields (`variant`, `version`, `resolved_via`), so the whole
    dict is returned; and, per this module's discipline, an unresolvable PDK
    aborts rendering rather than being papered over -- the PDK pin (issue
    #407) is evidence, not a nicety.
    """
    return json.loads(
        subprocess.run(
            [klt, "pdk", "find", "--pdk", pdk_variant, "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )


def build_argparser_strict() -> argparse.ArgumentParser:
    """The five-flag skeleton shared by the strict-discipline
    `render-record.py` scripts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--record-id", required=True)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--klt", required=True)
    parser.add_argument("--pdk-variant", required=True)
    return parser


def render_provenance_header(
    klt_version: str,
    drc: dict,
    pdk_info: dict,
    sha: str,
    branch: str,
    dirty: bool,
) -> list[str]:
    """Return the `## Provenance` header lines shared byte-for-byte by the
    `comparator`/`sampling-frontend`/`sampling-frontend-wells` flows: the
    section title and the four `klt`/KLayout/PDK/repo-commit bullets.

    Each caller's own DRC-deck bullet (and any further deck-specific lines)
    legitimately differ -- e.g. `sampling-frontend-wells` cites the n-well
    isolation rules its curated deck carries -- so those are appended by the
    caller after this header, not folded in here.
    """
    return [
        "## Provenance",
        "",
        f"- `klt` version: {klt_version}",
        f"- KLayout engine: {drc.get('provenance', {}).get('klayout_version')}",
        f"- PDK: {pdk_info.get('variant')} ({pdk_info.get('version')})",
        f"- PDK root: resolved via `{pdk_info.get('resolved_via')}`",
        f"- repo commit: `{sha}` on `{branch}`{' (dirty working tree)' if dirty else ''}",
    ]


def render_net_correspondence(lvs: dict) -> list[str]:
    """Return the `## Net correspondence (layout <-> reference)` section,
    byte-identical across the `comparator`/`sampling-frontend`/
    `sampling-frontend-wells` flows."""
    lines = ["## Net correspondence (layout <-> reference)", ""]
    for entry in lvs.get("net_correspondence", []):
        marker = "pin" if entry.get("pin") else "internal"
        lines.append(f"- `{entry.get('layout')}` <-> `{entry.get('reference')}` ({marker})")
    lines.append("")
    return lines


def render_lvs_findings(lvs: dict, title: str = "Reported LVS findings") -> list[str]:
    """Return the LVS findings section shared by the `comparator`/
    `sampling-frontend`/`sampling-frontend-wells` flows: a `## {title}`
    header, the `mismatches` list (or `- none`), and, on a `match` verdict, a
    closing sentence naming the interpolated `error_count`.

    `title` covers the header wording difference: `sampling-frontend` and
    `sampling-frontend-wells` both title this "Reported LVS findings (good
    reference)"; `comparator` omits the "(good reference)" suffix, since its
    LVS stage runs against only one reference, not a good/bad pair.
    """
    lines = [f"## {title}", ""]
    findings = lvs.get("mismatches", [])
    if not findings:
        lines.append("- none")
    for finding in findings:
        lines.append(
            f"- [{finding.get('severity')}] {finding.get('category')}: "
            f"{finding.get('description')}"
        )
    if lvs.get("status") == "match":
        lines.append("")
        lines.append(
            "Every finding above is reported at `severity: warning` with "
            f"`error_count = {lvs.get('error_count')}`; `klt lvs`'s own overall "
            f"verdict for this run is `{lvs.get('status')}`."
        )
    lines.append("")
    return lines

"""Shared "strict discipline" helpers for the layout `render-record.py`
scripts that require every stage to have already completed before rendering
runs.

Used by `layout/bin/render-record.py` (trivial-cell), `layout/comparator/bin/
render-record.py`, and `layout/sampling-frontend-wells/bin/render-record.py`
-- each imports this module via a `sys.path` insert (see any of the three
scripts' own header) rather than a package install, matching sim/harness/'s
no-extra-runtime-dependency convention.

Deliberately a **separate** module from `layout/bin/_record_common.py`, not a
merge into it. That module's docstring documents an intentional split: its
`load_json`/git helpers are lenient and missing-file-tolerant, for flows
(`layout/cdac-array/`, `layout/sar-sequencer/`) that are honest about
partial/blocked completion, where a missing JSON envelope means "that stage
hasn't run yet" rather than "something is broken". The three flows this
module serves are the opposite: they require full completion, so a missing or
malformed envelope should raise rather than degrade to `{}`. Folding either
flavor into the other would blur that intentional difference -- see
`_record_common.py`'s own docstring for the fuller rationale.
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

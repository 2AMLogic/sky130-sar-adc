"""Shared helpers for the layout sub-block `render-record.py` scripts.

Used by `layout/sar-sequencer/bin/render-record.py` and
`layout/cdac-array/bin/render-record.py`, which import this module via a
`sys.path` insert (see either script's own header) rather than a package
install, matching sim/harness/'s no-extra-runtime-dependency convention.

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

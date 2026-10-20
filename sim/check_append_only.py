#!/usr/bin/env python3
"""Append-only gate for `sim/` evidence (issue #599).

    python3 sim/check_append_only.py                         # local default
    python3 sim/check_append_only.py --base REV [--head REV]  # explicit base tree
    python3 sim/check_append_only.py --merge-base-of REV [--head REV]
    python3 sim/check_append_only.py --root DIR ...           # another checkout

`sim/README.md` ("Append-only rule") makes everything a simulation run leaves
behind append-only evidence: a record or raw artifact is never edited, deleted
or renamed once it exists, not even to fix a typo. Until this gate that rule
was enforced by prose and reviewer attention only, and an in-place edit is
silent everywhere else: the file stays well-formed, and every hash check
re-pins to the edited bytes. This script compares two committed trees and
fails if any **pre-existing** protected path was changed.

## What is protected (the policy, as data below)

Repository-relative path components, never a glob, and an experiment is
exactly one directory below `sim/`:

  * `sim/<experiment>/records/*.md`: direct Markdown children only.
  * every file, at any depth, below `sim/<experiment>/<dir>/` for each `<dir>`
    in `PROTECTED_ARTIFACT_DIRS` (`corners`, `mc-draws`, `netlist-snapshots`,
    `diagnostics`, `runs`, `yield-reports`). No extension filter applies:
    raw logs, frozen decks, JSON yield reports and persisted samples all
    carry evidence.

Excluded: `sim/<experiment>/records/LATEST` is a pointer that is meant to move
(sim/README.md, "The `records/LATEST` pointer"). It is not a `.md` file, so the
records rule never matches it; it is still listed in `MUTABLE_POINTERS` so
the carve-out stays reviewable. No basename-`LATEST` exception applies inside
the artifact directories. Everything else is outside this gate: experiment
READMEs, testbenches, runner/harness sources, `sim/pdk.json`, spec-coverage
files, tests, `docs/characterization-report.md`, and all of `layout/` and
`signoff/`. Layout reports and ERC records have their own append-only
convention and sign-off is regenerated deliberately, but this gate checks
neither, and makes no claim about them.

## What fails

Any `M` (modified), `D` (deleted), `R` (renamed) or `T` (type-changed) entry
in `git diff --name-status -z --find-renames=100% <base> <head>` whose
**pre-image** path is protected. A rename fails on its source, even when the
destination is outside the protected set. A rename that also edits the file
appears as `D` + `A` and fails on the `D`. Additions pass, including a record
that a branch added and then edited again, since it is absent from the base
tree. `C` (copy) leaves its source intact and is treated as an addition. Any
status this script does not recognise, or output it cannot parse, fails
rather than being dropped.

There is no override flag. A wrong record is corrected by minting a NEW record
whose **Supersedes** field names the one it replaces. That field is governed by
sim/check_supersedes_capability.py and read by the two citation gates.

## Which trees are compared

Only committed trees are compared. Staged and unstaged changes are not
checked: commit them first, or compare them separately.

  * `--base REV`: compare REV's tree directly to the head's tree. The caller
    chooses what REV means (a merge-base, a prior push SHA). Use this for a
    push to main: `github.event.before` against `github.sha` covers every
    commit in the push, and still sees evidence removed by a history rewrite.
  * `--merge-base-of REV`: compare `git merge-base REV <head>` to head. Use
    this for a PR, with REV = the PR base SHA and head = the PR head SHA
    (NOT the synthetic merge commit CI checks out).
  * neither (local default): `--merge-base-of origin/main`. On main itself
    this compares a commit to itself and checks no history. PR and main-push
    CI runs provide the history guard.
  * `--head REV` defaults to `HEAD`.

`APPEND_ONLY_BASE`, `APPEND_ONLY_MERGE_BASE_OF` and `APPEND_ONLY_HEAD` supply
the same values from the environment, so that `npm run check:ci` can forward
CI's event-specific revisions without a second invocation. CLI flags take
precedence over the environment. A variable that is set but empty is an error,
not "unset".

This script never fetches. It fails nonzero with a diagnostic when a revision
does not resolve, the base is the all-zero SHA (a branch-creation push), no
merge-base exists, a merge-base is requested in a shallow clone, or any git
command fails. Missing history never counts as a pass, and the script never
substitutes `HEAD` for a base it could not resolve. Checkout and fetch depth
are the caller's job (CI uses `fetch-depth: 0`).

Pure git plumbing: no ngspice, no PDK, no network. Runs in the headless
`checks` CI job via `npm run check:append-only`, which is part of `check:ci`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Policy (reviewable data). Changing any of these widens or narrows what the
# evidence trail is protected against -- treat an edit here as a policy change.
# --------------------------------------------------------------------------

#: Top-level directory every protected path lives under.
SIM_DIR = "sim"

#: `sim/<experiment>/records/<name>.md` (direct children only) is protected.
RECORDS_DIR = "records"
RECORD_SUFFIX = ".md"

#: Every file at any depth below `sim/<experiment>/<dir>/` is protected.
PROTECTED_ARTIFACT_DIRS = frozenset(
    {
        "corners",
        "mc-draws",
        "netlist-snapshots",
        "diagnostics",
        "runs",
        "yield-reports",
    }
)

#: Paths under `sim/<experiment>/` that are mutable by design. The records rule
#: does not match them anyway (no `.md` suffix); listed so the carve-out is
#: explicit. Applies only directly under `records/`, never inside an artifact
#: directory.
MUTABLE_POINTERS = frozenset({"records/LATEST"})

#: Statuses whose pre-image path is destroyed or altered by the change.
REJECTED_STATUSES = frozenset({"M", "D", "R", "T"})
#: Statuses that leave every pre-existing path intact.
ALLOWED_STATUSES = frozenset({"A", "C"})
#: Statuses carrying two paths (source, destination) in `-z` output.
TWO_PATH_STATUSES = frozenset({"R", "C"})

DEFAULT_MERGE_BASE_OF = "origin/main"

ENV_BASE = "APPEND_ONLY_BASE"
ENV_MERGE_BASE_OF = "APPEND_ONLY_MERGE_BASE_OF"
ENV_HEAD = "APPEND_ONLY_HEAD"

CORRECTION_ROUTE = (
    "Evidence under sim/ is append-only (sim/README.md, \"Append-only rule\"). "
    "Restore the original bytes and path. To correct a result, mint a NEW "
    "record whose **Supersedes** field names the one it replaces (see "
    "sim/check_supersedes_capability.py). There is no override flag."
)

_ZERO_SHA = re.compile(r"^0+$")


def is_protected(path: str) -> bool:
    """Whether a repository-relative, `/`-separated path is protected evidence."""
    parts = path.split("/")
    if len(parts) < 4 or parts[0] != SIM_DIR:
        return False
    if any(p == "" for p in parts):
        return False
    kind = parts[2]
    rest = "/".join(parts[2:])
    if kind == RECORDS_DIR:
        if rest in MUTABLE_POINTERS:
            return False
        return len(parts) == 4 and parts[3].endswith(RECORD_SUFFIX)
    return kind in PROTECTED_ARTIFACT_DIRS


class CheckError(Exception):
    """A comparison that cannot be made. Always a nonzero exit, never a pass."""


@dataclass(frozen=True)
class Change:
    status: str  # single letter, score stripped
    raw_status: str  # as git printed it, e.g. "R100"
    src: str  # pre-image path (== dst for one-path statuses)
    dst: str


@dataclass(frozen=True)
class Violation:
    change: Change

    def render(self) -> str:
        c = self.change
        if c.status in TWO_PATH_STATUSES:
            return f"{c.raw_status}\t{c.src!r} -> {c.dst!r}"
        return f"{c.raw_status}\t{c.src!r}"


def parse_name_status_z(out: bytes) -> list[Change]:
    """Parse `git diff --name-status -z` output.

    Format: `<status>\\0<path>\\0` for one-path statuses and
    `<status><score>\\0<src>\\0<dst>\\0` for R/C. Paths may contain any byte
    except NUL (spaces, tabs, newlines). Anything unexpected raises.
    """
    if not out:
        return []
    if not out.endswith(b"\0"):
        raise CheckError("git diff -z output is not NUL-terminated")
    fields = out[:-1].split(b"\0")
    changes: list[Change] = []
    i = 0
    while i < len(fields):
        raw = fields[i].decode("ascii") if fields[i].isascii() else None
        if not raw or not re.fullmatch(r"[A-Z][0-9]{0,3}", raw):
            raise CheckError(f"unparseable git diff status field {fields[i]!r}")
        status = raw[0]
        if status not in REJECTED_STATUSES | ALLOWED_STATUSES:
            raise CheckError(f"unexpected git diff status {raw!r}")
        n = 2 if status in TWO_PATH_STATUSES else 1
        if i + n >= len(fields):
            raise CheckError(f"truncated git diff entry for status {raw!r}")
        paths = [os.fsdecode(f) for f in fields[i + 1 : i + 1 + n]]
        if any(p == "" for p in paths):
            raise CheckError(f"empty path in git diff entry for status {raw!r}")
        src, dst = (paths[0], paths[-1])
        changes.append(Change(status=status, raw_status=raw, src=src, dst=dst))
        i += 1 + n
    return changes


def violations(changes: list[Change]) -> list[Violation]:
    return [
        Violation(c)
        for c in changes
        if c.status in REJECTED_STATUSES and is_protected(c.src)
    ]


# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------


def _git(root: Path, *args: str) -> bytes:
    cmd = ["git", "-C", str(root), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CheckError(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip() or "(no stderr)"
        raise CheckError(
            f"`git {' '.join(args)}` failed (exit {proc.returncode}): {err}"
        )
    return proc.stdout


def _is_shallow(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-shallow-repository").strip() == b"true"


def resolve_commit(root: Path, rev: str, role: str) -> str:
    if _ZERO_SHA.fullmatch(rev):
        raise CheckError(
            f"{role} revision is the all-zero SHA ({rev}): there is no prior "
            "tree to compare against (e.g. a branch-creation push). Supply an "
            "explicit base revision; this gate does not treat that as a pass."
        )
    if rev.startswith("-"):
        raise CheckError(f"{role} revision {rev!r} looks like an option")
    try:
        out = _git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    except CheckError as exc:
        hint = ""
        try:
            if _is_shallow(root):
                hint = (
                    " This is a shallow clone, so the commit may simply not "
                    "have been fetched: check out with full history "
                    "(actions/checkout `fetch-depth: 0`) or `git fetch "
                    "--unshallow`."
                )
        except CheckError:
            pass
        raise CheckError(
            f"{role} revision {rev!r} does not resolve to a commit in "
            f"{root}.{hint} This script never fetches; make the revision "
            "available first."
        ) from exc
    return out.decode().strip()


def merge_base(root: Path, other: str, head_sha: str) -> str:
    if _is_shallow(root):
        raise CheckError(
            f"refusing to compute a merge-base in a shallow clone ({root}): "
            "the true common ancestor may not have been fetched. Check out "
            "with full history (actions/checkout `fetch-depth: 0`) or run "
            "`git fetch --unshallow`."
        )
    other_sha = resolve_commit(root, other, "merge-base-of")
    cmd = ["git", "-C", str(root), "merge-base", other_sha, head_sha]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode == 1 and not proc.stdout.strip():
        raise CheckError(
            f"{other!r} ({other_sha}) and head ({head_sha}) share no common "
            "ancestor, so there is no base tree to compare against."
        )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip() or "(no stderr)"
        raise CheckError(f"`git merge-base` failed (exit {proc.returncode}): {err}")
    return proc.stdout.decode().strip()


def diff_changes(root: Path, base_sha: str, head_sha: str) -> list[Change]:
    out = _git(
        root,
        "-c", "core.quotepath=false",
        "diff",
        "--name-status",
        "-z",
        "--find-renames=100%",
        "--no-ext-diff",
        "--no-textconv",
        "--no-relative",
        "--ignore-submodules=none",
        base_sha,
        head_sha,
        "--",
    )
    return parse_name_status_z(out)


# --------------------------------------------------------------------------
# argument / environment resolution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    mode: str  # "base" | "merge-base-of"
    rev: str
    head: str
    source: str  # human-readable origin of the choice


def _env(env: Mapping[str, str], name: str) -> str | None:
    if name not in env:
        return None
    value = env[name]
    if value.strip() == "":
        raise CheckError(
            f"${name} is set but empty. Unset it to use the default, or give "
            "it a revision; an empty value is never treated as \"no base\"."
        )
    return value.strip()


def plan_comparison(args: argparse.Namespace, env: Mapping[str, str]) -> Plan:
    if args.base is not None:
        mode, rev, source = "base", args.base, "--base"
    elif args.merge_base_of is not None:
        mode, rev, source = "merge-base-of", args.merge_base_of, "--merge-base-of"
    else:
        env_base = _env(env, ENV_BASE)
        env_mbo = _env(env, ENV_MERGE_BASE_OF)
        if env_base is not None and env_mbo is not None:
            raise CheckError(
                f"both ${ENV_BASE} and ${ENV_MERGE_BASE_OF} are set; set exactly one"
            )
        if env_base is not None:
            mode, rev, source = "base", env_base, f"${ENV_BASE}"
        elif env_mbo is not None:
            mode, rev, source = "merge-base-of", env_mbo, f"${ENV_MERGE_BASE_OF}"
        else:
            mode, rev, source = (
                "merge-base-of",
                DEFAULT_MERGE_BASE_OF,
                "local default",
            )
    for flag, value in (
        ("--base", args.base),
        ("--merge-base-of", args.merge_base_of),
        ("--head", args.head),
    ):
        if value is not None and value.strip() == "":
            raise CheckError(f"{flag} was given an empty revision")
    if args.head is not None:
        head = args.head
    else:
        head = _env(env, ENV_HEAD) or "HEAD"
    return Plan(mode=mode, rev=rev, head=head, source=source)


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--root", default=str(REPO_ROOT), help="repo root (default: this checkout)"
    )
    group = ap.add_mutually_exclusive_group()
    group.add_argument(
        "--base",
        help=f"compare this revision's tree directly to head (env: ${ENV_BASE})",
    )
    group.add_argument(
        "--merge-base-of",
        help=(
            "compare `git merge-base REV head` to head "
            f"(env: ${ENV_MERGE_BASE_OF}; default: {DEFAULT_MERGE_BASE_OF})"
        ),
    )
    ap.add_argument("--head", help=f"head revision (env: ${ENV_HEAD}; default: HEAD)")
    args = ap.parse_args(argv)
    root = Path(args.root)

    try:
        plan = plan_comparison(args, env)
        head_sha = resolve_commit(root, plan.head, "head")
        if plan.mode == "base":
            base_sha = resolve_commit(root, plan.rev, "base")
            how = f"base {plan.rev} ({plan.source})"
        else:
            base_sha = merge_base(root, plan.rev, head_sha)
            how = f"merge-base of {plan.rev} and head ({plan.source})"
        print(f"append-only: base {base_sha} = {how}")
        print(f"append-only: head {head_sha} = {plan.head}")
        if base_sha == head_sha:
            print(
                "append-only: base and head are the same commit -- zero diff, "
                "so no historical change is checked by this run (PR and "
                "main-push CI runs provide the history guard)."
            )
        changes = diff_changes(root, base_sha, head_sha)
    except CheckError as exc:
        sys.stdout.flush()
        print(
            f"FAIL: append-only check could not compare trees: {exc}",
            file=sys.stderr,
        )
        return 2

    bad = violations(changes)
    if bad:
        sys.stdout.flush()
        print(
            f"FAIL: append-only check: {len(bad)} existing sim/ evidence "
            f"path(s) changed between {base_sha} and {head_sha}",
            file=sys.stderr,
        )
        for v in bad:
            print(f"  {v.render()}", file=sys.stderr)
        print(f"\n{CORRECTION_ROUTE}", file=sys.stderr)
        return 1

    added = sum(
        1 for c in changes if c.status in ALLOWED_STATUSES and is_protected(c.dst)
    )
    added += sum(
        1
        for c in changes
        if c.status == "R" and not is_protected(c.src) and is_protected(c.dst)
    )
    print(
        f"OK: {len(changes)} changed path(s), {added} new sim/ evidence "
        "path(s), no existing evidence modified, deleted, renamed or "
        "type-changed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

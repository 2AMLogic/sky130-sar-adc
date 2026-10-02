#!/usr/bin/env python3
"""Supersession-capability check -- every evidence-writing runner must be able
to say what its record replaces (issue #502).

    python3 sim/check_supersedes_capability.py            # check (exit 1 on failure)
    python3 sim/check_supersedes_capability.py --root DIR  # check another tree

`sim/README.md`'s append-only convention makes a record's **Supersedes** field
the *only* machine-readable statement that a re-run replaces an earlier result
for the same claim. Two live gates read it:

  * `sim/report/generate.py --check` (`npm run check:report`) -- fails when
    `sim/report/manifest.py` cites a record that a sibling record declares it
    supersedes (`find_superseding_sibling()`).
  * `docs/chipalooza/check_proposal_citations.py` check 3 -- the same question
    asked of the Chipalooza proposal's citations.

Both gates are therefore only as good as the field's population. A runner that
writes a record but cannot populate it does not make those gates *fail* -- it
makes them **stay quiet**, which is indistinguishable from "the citation is
fresh". That is exactly how issue #498's six re-runs went: four of the six new
records could not declare what they displaced, the gates said nothing, and the
stale citations had to be found by hand. The gap was invisible until a re-run
happened, and at that moment the person re-running is the one least likely to
notice a silent gate. So it is checked mechanically here instead.

## What is enforced

THREADING (static, AST) -- no `harness.evidence.footer_lines()` call site may
pass a bare literal `""` as its `supersedes` argument. A bare `""` is
unreadable: it looks identical whether the author meant "this record replaces
nothing, by construction" or forgot to thread the runner's own `--supersedes`
flag into this particular write path. That second shape is a real bug this repo
has already shipped once -- issue #498 found
`sim/cdac-array-transfer/run_transfer.py` declaring `--supersedes` and
threading it into only ONE of its two record writers, so `--ratified-record`
accepted the flag and silently wrote `Supersedes: (none)`. A write path that
genuinely never supersedes anything says so by name, with
`evidence.NEVER_SUPERSEDES` (same value, zero record-byte difference, but a
deliberate and reviewable statement -- see the three `diagnostics/` writers in
sim/full-conversion-transient/run_conversion.py).

CALL SITES (static, AST) -- a record-writing function that forwards a parameter
to `footer_lines()` must be *called* with that parameter supplied, everywhere.
This is the same silent failure one level up the call stack, and the only one
the other two checks cannot see: the flag is declared, the writer forwards a
name rather than a literal, and `main()` still never passes it, so the record
reads `Supersedes: (none)` however the runner was invoked.

CLI SURFACE (dynamic, `--help`) -- every runner entry point whose own usage
line advertises `--record` must also advertise `--supersedes`. Checked by
actually running `<runner> --help` and reading argparse's usage block, not by
grepping the source: that is what proves the flag is really *accepted* (and it
follows the indirection for free -- `sim/run_corners.py` and
`sim/monte_carlo.py` declare nothing themselves, inheriting the flag from
`sim/harness/cli.py` / `mc_cli.py`). Reading the usage block specifically, not
the whole help text, is deliberate: a runner's prose help may *mention*
`--supersedes` while not defining it, which is precisely the false pass this
check must not give.

  Not probed at all: a `sim/**/*.py` script with a `__main__` guard but no
  argparse CLI of its own and none it delegates to (e.g. a fragment generator
  that ignores its argv). It has no flags to check, and not probing it keeps
  this check from executing code it has no question about.

  Exempt: a runner every one of whose `footer_lines()` call sites passes a
  non-empty literal (an f-string naming a specific displaced record). Those
  records DO populate **Supersedes**, so both gates can already see a stale
  citation of them -- the harm this check exists to prevent does not apply,
  which is why making a hardcoded pointer CLI-settable was always a separate
  improvement rather than a silent gate.

  As of issue #513 that exemption is unexercised: its two users
  (sim/sampling-acquisition-settling/ and sim/vcm-drive-budget/) now take
  `--supersedes` too, with their old hardcoded narrative as the flag's
  DEFAULT -- byte-identical records when the flag is omitted, re-aimable
  without editing source when a re-run displaces something else. The branch
  is kept (tested on synthetic fixtures in
  sim/tests/test_supersedes_capability.py) because the shape it describes is
  still a legitimate one for a brand-new runner; nothing in this repo relies
  on it today.

Pure file reads plus one `--help` subprocess per runner: no ngspice, no PDK, no
network. Runs in the headless `checks` CI job (`npm run check:ci`) alongside
sim/check_spec_coverage.py.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The name a write path uses to opt out of supersession explicitly. Kept as a
#: string rather than imported from harness.evidence so this check stays a pure
#: source reader (and keeps working on a tree whose harness does not import).
OPT_OUT_NAME = "NEVER_SUPERSEDES"

#: Flags that mean "this invocation writes an evidence record". `--record` is
#: the repo-wide convention (sim/README.md); run_transfer.py's extra
#: `--ratified-record` is a second writing mode of the same runner.
RECORD_FLAGS = ("--record", "--ratified-record")

SUPERSEDES_FLAG = "--supersedes"

HELP_TIMEOUT_S = 120


@dataclass(frozen=True)
class Problem:
    kind: str
    where: str
    detail: str

    def render(self) -> str:
        return f"[{self.kind}] {self.where}: {self.detail}"


@dataclass(frozen=True)
class FooterCall:
    """One `footer_lines()` call site and the shape of its `supersedes`
    argument."""

    path: Path
    lineno: int
    #: `ast.unparse()` of the argument, for the failure message.
    source: str
    #: True when the argument is a bare literal empty string.
    is_bare_empty: bool
    #: True when the argument is a NON-EMPTY literal (a string constant or
    #: f-string naming the specific record this path displaces) rather than a
    #: name threaded in from a flag. An empty literal is NOT one of these: it
    #: names no record, which is the whole problem.
    is_hardcoded_pointer: bool


def _supersedes_arg(call: ast.Call) -> ast.expr | None:
    """The `supersedes` argument of a `footer_lines()` call, positionally
    (index 1, after `written_by`) or by keyword. None if absent -- which
    `footer_lines()`'s own signature already makes a TypeError, so it is not
    separately reported here."""
    if len(call.args) > 1:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg == "supersedes":
            return kw.value
    return None


def footer_calls(py_path: Path) -> list[FooterCall]:
    """Every `footer_lines()` call site in `py_path`, classified. Matches on
    the called name (`evidence.footer_lines` or a bare `footer_lines`) rather
    than on text, so a mention in a docstring or comment is not a call."""
    src = py_path.read_text(encoding="utf-8")
    if "footer_lines" not in src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []  # npm run test:compile owns syntax; do not double-report

    calls: list[FooterCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "footer_lines":
            continue
        arg = _supersedes_arg(node)
        if arg is None:
            continue
        is_opt_out = (
            isinstance(arg, ast.Attribute) and arg.attr == OPT_OUT_NAME
        ) or (isinstance(arg, ast.Name) and arg.id == OPT_OUT_NAME)
        is_const_empty = isinstance(arg, ast.Constant) and arg.value == ""
        calls.append(
            FooterCall(
                path=py_path,
                lineno=node.lineno,
                source=ast.unparse(arg),
                is_bare_empty=is_const_empty and not is_opt_out,
                is_hardcoded_pointer=(
                    isinstance(arg, (ast.Constant, ast.JoinedStr))
                    and not is_const_empty
                ),
            )
        )
    return calls


def _param_position(func: ast.FunctionDef, name: str) -> int | None:
    """Index of parameter `name` in `func`'s positional parameter list, or
    None if it is not a positional-or-keyword parameter."""
    params = [a.arg for a in func.args.posonlyargs + func.args.args]
    return params.index(name) if name in params else None


def unthreaded_writers(py_path: Path) -> list[tuple[str, int, str]]:
    """`(writer_name, call_lineno, param_name)` for every call, inside
    `py_path`, of a record-writing function that forwards a parameter to
    `footer_lines()` but is invoked WITHOUT supplying that parameter -- so the
    write silently falls back to the parameter's `""` default.

    This is the third shape of the same silent failure, and the one neither
    other check sees: the flag is declared (CLI check passes) and the writer
    forwards a name rather than a literal (threading check passes), yet
    `main()` never passes it, so the record still says `(none)`. It is issue
    #498's bug generalized one level up the call stack."""
    src = py_path.read_text(encoding="utf-8")
    if "footer_lines" not in src:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []

    # writer name -> (parameter name, positional index)
    writers: dict[str, tuple[str, int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            fn = inner.func
            fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if fname != "footer_lines":
                continue
            arg = _supersedes_arg(inner)
            if not isinstance(arg, ast.Name) or arg.id == OPT_OUT_NAME:
                continue
            position = _param_position(node, arg.id)
            if position is not None:
                writers[node.name] = (arg.id, position)

    problems: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        entry = writers.get(node.func.id)
        if entry is None:
            continue
        param, position = entry
        supplied = len(node.args) > position or any(
            kw.arg == param for kw in node.keywords
        )
        if not supplied:
            problems.append((node.func.id, node.lineno, param))
    return problems


def python_sources(root: Path) -> list[Path]:
    """Every `sim/**/*.py` except the test suite's own fixtures (which
    deliberately construct failing shapes)."""
    sim = root / "sim"
    return [
        p
        for p in sorted(sim.rglob("*.py"))
        if "tests" not in p.relative_to(sim).parts
    ]


def _argparse_candidates(py_path: Path, root: Path) -> list[Path]:
    """Modules a `from <mod> import main` in `py_path` could resolve to. Lets
    the delegating entry points (`sim/run_corners.py` ->
    `sim/harness/cli.py`) be recognised as CLIs without executing anything."""
    src = py_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out: list[Path] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not any(alias.name == "main" for alias in node.names):
            continue
        parts = node.module.split(".")
        for base in (root / "sim", py_path.parent):
            out.append(base.joinpath(*parts).with_suffix(".py"))
    return out


def has_argparse_surface(py_path: Path, root: Path) -> bool:
    """Whether `py_path` presents an argparse CLI -- its own, or one it
    delegates to via `from <mod> import main`. Scripts with neither (e.g. a
    pure fragment generator that ignores its argv) are never probed, so this
    check does not execute code that has no flags to check."""
    if "ArgumentParser" in py_path.read_text(encoding="utf-8"):
        return True
    for candidate in _argparse_candidates(py_path, root):
        if candidate.is_file() and "ArgumentParser" in candidate.read_text(
            encoding="utf-8"
        ):
            return True
    return False


def entry_points(root: Path) -> list[Path]:
    """Every `sim/**/*.py` runnable as a script (has a `__main__` guard) that
    presents an argparse CLI. Includes the delegating `sim/run_corners.py` /
    `sim/monte_carlo.py`, which define no flags of their own."""
    found: list[Path] = []
    for p in python_sources(root):
        src = p.read_text(encoding="utf-8")
        if '__name__ == "__main__"' not in src and "__name__ == '__main__'" not in src:
            continue
        if has_argparse_surface(p, root):
            found.append(p)
    return found


def usage_block(help_text: str) -> str:
    """argparse's usage block: from `usage:` up to the first blank line. The
    only part of `--help` that lists what the parser actually DEFINES -- option
    help bodies are prose and may name a flag the parser does not define."""
    lines = help_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.startswith("usage:"))
    except StopIteration:
        return ""
    out: list[str] = []
    for ln in lines[start:]:
        if not ln.strip():
            break
        out.append(ln)
    return "\n".join(out)


def runner_usage(path: Path) -> tuple[str | None, str]:
    """`(usage_block, diagnostic)` for `python3 <path> --help`. A usage block
    of None means the probe itself failed -- reported as a failure, never
    skipped: a runner whose `--help` does not work cannot be shown to offer
    the flag."""
    try:
        proc = subprocess.run(
            [sys.executable, str(path), "--help"],
            capture_output=True,
            text=True,
            timeout=HELP_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return None, f"--help did not finish within {HELP_TIMEOUT_S}s"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
        return None, f"--help exited {proc.returncode}: {tail[0]}"
    block = usage_block(proc.stdout + proc.stderr)
    if not block:
        return None, "--help printed no argparse usage block"
    return block, ""


def advertises(usage: str, flag: str) -> bool:
    """Whether argparse's usage block lists `flag` as an option of its own.
    Guards against `--record` matching inside `--ratified-record` by requiring
    a non-flag character (or end of token) before the flag."""
    for raw in usage.replace("[", " ").replace("]", " ").split():
        token = raw.split("=", 1)[0]
        if token == flag:
            return True
    return False


def check(root: Path) -> list[Problem]:
    problems: list[Problem] = []

    # --- THREADING: no bare "" at any footer_lines() call site.
    calls_by_file: dict[Path, list[FooterCall]] = {}
    for py_path in python_sources(root):
        calls = footer_calls(py_path)
        if calls:
            calls_by_file[py_path] = calls
        for call in calls:
            if not call.is_bare_empty:
                continue
            problems.append(
                Problem(
                    "supersedes-dropped",
                    f"{call.path.relative_to(root)}:{call.lineno}",
                    "footer_lines() is passed a bare literal \"\" as `supersedes`, so "
                    "this record-writing path can never declare what it replaces -- "
                    "and a reader cannot tell a deliberate choice from a forgotten "
                    "one (issue #498's bug shape). Thread the runner's own "
                    "--supersedes flag in, or, if this path supersedes nothing by "
                    f"construction, say so by name with evidence.{OPT_OUT_NAME}.",
                )
            )
        for writer, lineno, param in unthreaded_writers(py_path):
            problems.append(
                Problem(
                    "supersedes-not-passed",
                    f"{py_path.relative_to(root)}:{lineno}",
                    f"{writer}() forwards its `{param}` parameter to "
                    f"footer_lines(), but this call omits it -- the record falls "
                    f"back to the parameter's \"\" default and writes "
                    "`Supersedes: (none)` however the runner was invoked. Pass "
                    f"{param}=args.{param} here.",
                )
            )

    # --- CLI SURFACE: a record-writing entry point must offer --supersedes.
    for path in entry_points(root):
        usage, diagnostic = runner_usage(path)
        rel = path.relative_to(root)
        if usage is None:
            problems.append(Problem("runner-help-failed", str(rel), diagnostic))
            continue
        if not any(advertises(usage, flag) for flag in RECORD_FLAGS):
            continue  # not a record writer
        if advertises(usage, SUPERSEDES_FLAG):
            continue
        own_calls = calls_by_file.get(path, [])
        if own_calls and all(c.is_hardcoded_pointer for c in own_calls):
            continue  # hardcoded supersession narrative -- see module docstring
        problems.append(
            Problem(
                "supersedes-flag-missing",
                str(rel),
                "writes an evidence record (its usage advertises "
                f"{'/'.join(f for f in RECORD_FLAGS if advertises(usage, f))}) but "
                f"offers no {SUPERSEDES_FLAG}, so a re-run cannot state which record "
                "it replaces and neither sim/report/generate.py --check nor "
                "docs/chipalooza/check_proposal_citations.py can detect a stale "
                "citation of it. Add it with "
                "harness.evidence.add_supersedes_argument(parser) and thread it to "
                "footer_lines() on EVERY write path this runner has.",
            )
        )

    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root", default=str(REPO_ROOT), help="repo root (default: this checkout)"
    )
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    problems = check(root)
    if problems:
        print(
            f"FAIL: supersession-capability check ({len(problems)} problem(s))",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem.render()}", file=sys.stderr)
        print(
            "\nSee sim/check_supersedes_capability.py's module docstring for what "
            "each check enforces, and sim/README.md for the append-only "
            "**Supersedes** convention it protects.",
            file=sys.stderr,
        )
        return 1

    n_runners = len(entry_points(root))
    n_calls = sum(len(footer_calls(p)) for p in python_sources(root))
    print(
        f"OK: {n_calls} evidence-record write path(s) across {n_runners} runner "
        "entry point(s) -- every one either threads --supersedes, names a "
        f"specific displaced record, or opts out explicitly via {OPT_OUT_NAME}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

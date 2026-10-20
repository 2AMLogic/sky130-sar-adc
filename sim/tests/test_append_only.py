"""Unit tests for sim/check_append_only.py (issue #599: the `sim/` append-only
rule had no mechanical gate, only prose and reviewer attention).

No ngspice/PDK/network required: every case builds a throwaway git repository
in a temp directory and runs the checker against it. The point is that the gate
is **fail-closed on synthetic history**, not merely green on this repo's: a
test that only asserted "the real tree passes" would keep passing if the
detection logic were gutted. So every failure shape is reproduced here:

- modify / delete across all eight protected classes (records plus the six
  raw-artifact directories, nested artifacts included);
- rename out of protection, rename-with-edit (D+A), protected-to-protected
  rename, type change, and hostile filenames (space, tab, newline);
- the invocation contracts: feature-branch merge-base, explicit PR head rather
  than the synthetic merge commit, a multi-commit push compared directly to its
  prior SHA (including a history rewrite), CLI/environment precedence, and
  every "cannot compare" path (absent ref, shallow clone, no common ancestor,
  all-zero base, git failure), each of which must exit nonzero.

And the allowed shapes: additions, a new record edited again inside the same
branch, `records/LATEST` moves, ordinary source/doc edits, and layout/sign-off
paths, which this simulation-only gate deliberately does not cover.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

import check_append_only as checker  # noqa: E402

ZERO = "0" * 40

#: One representative path per protected class (records + six artifact dirs,
#: two of them nested deeper than one level), plus a `LATEST`-named file inside
#: an artifact dir, which gets no pointer exemption.
PROTECTED_SAMPLES = {
    "records": "sim/exp-a/records/20260101-000000-abc1234.md",
    "corners": "sim/exp-a/corners/20260101-000000-abc1234/tt_27c_1.80v.log",
    "mc-draws": "sim/exp-a/mc-draws/20260101-000000-abc1234/draw_0_seed1.log",
    "netlist-snapshots": "sim/exp-a/netlist-snapshots/20260101-000000-abc1234.spice",
    "diagnostics": "sim/exp-a/diagnostics/20260101-000000-abc1234/sub/deep/trace.csv",
    "runs": "sim/exp-a/runs/20260101-000000-abc1234.log",
    "yield-reports": "sim/exp-a/yield-reports/20260101-000000-abc1234/yield.json",
    "yield-samples": "sim/exp-a/yield-reports/20260101-000000-abc1234/samples.json",
    "artifact-LATEST": "sim/exp-a/corners/LATEST",
}

#: Paths that must stay editable: the mutable pointer, experiment sources,
#: harness, shared config, tests, generated report, and the out-of-scope
#: layout/sign-off evidence (including their own LATEST pointers).
UNPROTECTED_SAMPLES = [
    "sim/exp-a/records/LATEST",
    "sim/exp-a/README.md",
    "sim/exp-a/testbench/tb.json",
    "sim/exp-a/testbench/frag.spice",
    "sim/exp-a/run_thing.py",
    "sim/harness/evidence.py",
    "sim/pdk.json",
    "sim/spec-coverage.json",
    "sim/tests/test_something.py",
    "sim/exp-a/records/nested/not-direct.md",
    "sim/exp-a/records/notes.txt",
    "sim/records/top-level.md",
    "sim/exp-a/sub/records/deeper.md",
    "docs/characterization-report.md",
    "layout/flow/reports/20260101-000000-abc1234/report.md",
    "layout/flow/reports/LATEST",
    "layout/flow/erc-reports/20260101-000000-abc1234.md",
    "signoff/block-manifest.json",
    "signoff/t1-report.json",
    "signoff/evidence/thing.json",
]


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
    )
    for name in (checker.ENV_BASE, checker.ENV_MERGE_BASE_OF, checker.ENV_HEAD):
        env.pop(name, None)
    return env


class Repo:
    """A throwaway git repository with small helpers."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"git {args} failed: {proc.stderr}")
        return proc.stdout.strip()

    def write(self, rel: str, content: str = "x\n") -> None:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_symlink():
            p.unlink()
        p.write_text(content)

    def remove(self, rel: str) -> None:
        (self.path / rel).unlink()

    def commit(self, msg: str = "c") -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)
        return self.sha()

    def sha(self, rev: str = "HEAD") -> str:
        return self.git("rev-parse", rev)


class GitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git not available")
        patcher = mock.patch.dict(os.environ, _clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.repo = Repo(self.tmp / "repo")
        self.repo.write("README.md", "root\n")
        self.base = self.repo.commit("base")

    def run_checker(
        self, *argv: str, env: dict[str, str] | None = None, root: Path | None = None
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        args = ["--root", str(root or self.repo.path), *argv]
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = checker.main(args, env=env if env is not None else {})
        return rc, out.getvalue(), err.getvalue()

    def assert_violation(self, rc: int, err: str, *paths: str) -> None:
        self.assertEqual(rc, 1, err)
        for p in paths:
            self.assertIn(repr(p), err)
        self.assertIn("Supersedes", err)
        self.assertIn("no override flag", err)

    def assert_cannot_compare(self, rc: int, err: str, needle: str) -> None:
        self.assertEqual(rc, 2, err)
        self.assertIn("could not compare", err)
        self.assertIn(needle, err)


class PolicyTest(unittest.TestCase):
    def test_protected_samples(self) -> None:
        for name, path in PROTECTED_SAMPLES.items():
            with self.subTest(name):
                self.assertTrue(checker.is_protected(path), path)

    def test_unprotected_samples(self) -> None:
        for path in UNPROTECTED_SAMPLES:
            with self.subTest(path):
                self.assertFalse(checker.is_protected(path), path)

    def test_policy_is_data(self) -> None:
        self.assertEqual(
            checker.PROTECTED_ARTIFACT_DIRS,
            {"corners", "mc-draws", "netlist-snapshots", "diagnostics", "runs",
             "yield-reports"},
        )
        self.assertIn("records/LATEST", checker.MUTABLE_POINTERS)


class ParserTest(unittest.TestCase):
    def test_parses_hostile_names(self) -> None:
        out = b"M\0a b\tc\nd\0R100\0x\0y z\0A\0new\0"
        changes = checker.parse_name_status_z(out)
        self.assertEqual(
            [(c.status, c.src, c.dst) for c in changes],
            [("M", "a b\tc\nd", "a b\tc\nd"), ("R", "x", "y z"), ("A", "new", "new")],
        )

    def test_rejects_unexpected_status(self) -> None:
        for bad in (b"X\0p\0", b"U\0p\0", b"B50\0p\0", b"??\0p\0"):
            with self.subTest(bad), self.assertRaises(checker.CheckError):
                checker.parse_name_status_z(bad)

    def test_rejects_truncated_or_unterminated(self) -> None:
        for bad in (b"R100\0only-src\0", b"M\0p", b"M\0", b"M\0\0"):
            with self.subTest(bad), self.assertRaises(checker.CheckError):
                checker.parse_name_status_z(bad)


class ProtectedClassTest(GitTestCase):
    def _seed(self) -> str:
        for path in PROTECTED_SAMPLES.values():
            self.repo.write(path, "original\n")
        return self.repo.commit("evidence")

    def test_modify_each_class_fails(self) -> None:
        seeded = self._seed()
        for name, path in PROTECTED_SAMPLES.items():
            with self.subTest(name):
                self.repo.git("checkout", "-q", "-B", f"mod-{name}", seeded)
                self.repo.write(path, "edited\n")
                self.repo.commit(f"edit {name}")
                rc, _, err = self.run_checker("--base", seeded)
                self.assert_violation(rc, err, path)
                self.assertIn("M\t", err)

    def test_delete_each_class_fails(self) -> None:
        seeded = self._seed()
        for name, path in PROTECTED_SAMPLES.items():
            with self.subTest(name):
                self.repo.git("checkout", "-q", "-B", f"del-{name}", seeded)
                self.repo.remove(path)
                self.repo.commit(f"delete {name}")
                rc, _, err = self.run_checker("--base", seeded)
                self.assert_violation(rc, err, path)
                self.assertIn("D\t", err)

    def test_add_each_class_passes(self) -> None:
        for path in PROTECTED_SAMPLES.values():
            self.repo.write(path, "new\n")
        self.repo.commit("add evidence")
        rc, out, err = self.run_checker("--base", self.base)
        self.assertEqual(rc, 0, err)
        self.assertIn(f"{len(PROTECTED_SAMPLES)} new sim/ evidence", out)


class RenameAndTypeTest(GitTestCase):
    REC = PROTECTED_SAMPLES["records"]

    def setUp(self) -> None:
        super().setUp()
        self.repo.write(self.REC, "record body\n" * 20)
        self.seeded = self.repo.commit("record")

    def test_pure_rename_out_of_protection_fails(self) -> None:
        self.repo.git("mv", self.REC, "sim/exp-a/archived.md")
        self.repo.commit("rename away")
        rc, _, err = self.run_checker("--base", self.seeded)
        self.assert_violation(rc, err, self.REC)
        self.assertIn("R100\t", err)

    def test_protected_to_protected_rename_fails(self) -> None:
        dst = "sim/exp-a/records/20990101-000000-fffffff.md"
        self.repo.git("mv", self.REC, dst)
        self.repo.commit("rename within")
        rc, _, err = self.run_checker("--base", self.seeded)
        self.assert_violation(rc, err, self.REC)

    def test_changed_rename_is_delete_plus_add_and_fails(self) -> None:
        dst = "sim/exp-a/records/20990101-000000-fffffff.md"
        self.repo.git("mv", self.REC, dst)
        self.repo.write(dst, "record body\n" * 19 + "changed\n")
        self.repo.commit("rename + edit")
        rc, _, err = self.run_checker("--base", self.seeded)
        self.assert_violation(rc, err, self.REC)
        self.assertIn("D\t", err)

    def test_type_change_fails(self) -> None:
        self.repo.remove(self.REC)
        os.symlink("elsewhere.md", self.repo.path / self.REC)
        self.repo.commit("file -> symlink")
        rc, _, err = self.run_checker("--base", self.seeded)
        self.assert_violation(rc, err, self.REC)
        self.assertIn("T\t", err)

    def test_unprotected_to_new_protected_rename_passes(self) -> None:
        self.repo.write("sim/exp-a/draft.md", "draft\n" * 10)
        start = self.repo.commit("draft")
        self.repo.git("mv", "sim/exp-a/draft.md", "sim/exp-a/records/20990101-x.md")
        self.repo.commit("promote draft")
        rc, out, err = self.run_checker("--base", start)
        self.assertEqual(rc, 0, err)
        self.assertIn("1 new sim/ evidence", out)

    def test_hostile_filenames(self) -> None:
        names = [
            "sim/exp b/records/with space.md",
            "sim/exp-a/records/tab\there.md",
            "sim/exp-a/corners/r/new\nline.log",
        ]
        for n in names:
            self.repo.write(n, "orig\n" * 10)
        start = self.repo.commit("hostile")
        self.repo.write(names[0], "edited\n")
        self.repo.remove(names[1])
        self.repo.git("mv", names[2], "sim/exp-a/moved\nout.log")
        self.repo.commit("mutate hostile")
        rc, _, err = self.run_checker("--base", start)
        self.assert_violation(rc, err, *names)
        self.assertIn("3 existing sim/ evidence", err)


class AllowedChangesTest(GitTestCase):
    def test_unprotected_edits_pass(self) -> None:
        for p in UNPROTECTED_SAMPLES:
            self.repo.write(p, "v1\n")
        start = self.repo.commit("seed")
        for p in UNPROTECTED_SAMPLES:
            self.repo.write(p, "v2\n")
        self.repo.remove("layout/flow/erc-reports/20260101-000000-abc1234.md")
        self.repo.remove("signoff/evidence/thing.json")
        self.repo.commit("edit everything unprotected")
        rc, out, err = self.run_checker("--base", start)
        self.assertEqual(rc, 0, err)
        self.assertIn("OK:", out)

    def test_latest_pointer_moves(self) -> None:
        self.repo.write("sim/exp-a/records/a.md", "a\n")
        self.repo.write("sim/exp-a/records/LATEST", "a.md\n")
        start = self.repo.commit("first")
        self.repo.write("sim/exp-a/records/b.md", "b\n")
        self.repo.write("sim/exp-a/records/LATEST", "b.md\n")
        self.repo.commit("second")
        rc, _, err = self.run_checker("--base", start)
        self.assertEqual(rc, 0, err)

    def test_new_record_edited_within_branch_passes(self) -> None:
        self.repo.git("checkout", "-q", "-b", "feature")
        rec = "sim/exp-a/records/20990101-000000-fffffff.md"
        self.repo.write(rec, "draft\n")
        self.repo.commit("add")
        self.repo.write(rec, "fixed typo\n")
        self.repo.commit("edit own new record")
        rc, _, err = self.run_checker("--merge-base-of", "main")
        self.assertEqual(rc, 0, err)
        # ...but the same edit IS a violation relative to the intermediate commit.
        rc, _, err = self.run_checker("--base", "HEAD~1")
        self.assert_violation(rc, err, rec)


class InvocationContractTest(GitTestCase):
    REC = "sim/exp-a/records/r1.md"

    def setUp(self) -> None:
        super().setUp()
        self.repo.write(self.REC, "r1\n")
        self.main1 = self.repo.commit("main: r1")

    def test_feature_branch_uses_merge_base(self) -> None:
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.write("sim/exp-a/run.py", "print(1)\n")
        self.repo.commit("feature work")
        self.repo.git("checkout", "-q", "main")
        self.repo.write("sim/exp-a/records/r2.md", "r2\n")
        self.repo.commit("main: r2 (after branch point)")
        self.repo.git("checkout", "-q", "feature")
        # Directly against main's tip, r2 looks deleted on the branch...
        rc, _, err = self.run_checker("--base", "main")
        self.assert_violation(rc, err, "sim/exp-a/records/r2.md")
        # ...the merge-base comparison only sees the branch's own changes.
        rc, out, err = self.run_checker("--merge-base-of", "main")
        self.assertEqual(rc, 0, err)
        self.assertIn(f"base {self.main1}", out)

    def test_explicit_pr_head_not_synthetic_merge(self) -> None:
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.write(self.REC, "tampered\n")
        pr_head = self.repo.commit("tamper")
        self.repo.git("checkout", "-q", "main")
        self.repo.write("docs/x.md", "x\n")
        pr_base = self.repo.commit("main moves")
        # CI checks out a synthetic merge commit; HEAD is that, not the PR head.
        self.repo.git("checkout", "-q", "--detach", pr_base)
        self.repo.git("merge", "-q", "--no-edit", "--no-ff", pr_head)
        synthetic = self.repo.sha()
        self.assertNotEqual(synthetic, pr_head)
        rc, out, err = self.run_checker(
            "--merge-base-of", pr_base, "--head", pr_head
        )
        self.assert_violation(rc, err, self.REC)
        self.assertIn(f"head {pr_head}", out)
        self.assertIn(f"base {self.main1}", out)
        # With HEAD back on a clean main, the explicit head is still what is checked.
        self.repo.git("checkout", "-q", "main")
        rc, _, err = self.run_checker("--merge-base-of", pr_base, "--head", pr_head)
        self.assert_violation(rc, err, self.REC)

    def test_multi_commit_push_compared_to_prior_sha(self) -> None:
        before = self.main1
        self.repo.write("sim/exp-a/records/r2.md", "r2\n")
        self.repo.commit("push commit 1: add r2")
        self.repo.write("sim/exp-a/records/r2.md", "r2 edited\n")
        clean_push = self.repo.commit("push commit 2: edit r2 (new in this push)")
        rc, _, err = self.run_checker("--base", before, "--head", clean_push)
        self.assertEqual(rc, 0, err)
        self.repo.write(self.REC, "r1 edited\n")
        self.repo.commit("push commit 3: edit r1 (pre-existing)")
        self.repo.write("README.md", "unrelated\n")
        after = self.repo.commit("push commit 4: unrelated")
        rc, _, err = self.run_checker("--base", before, "--head", after)
        self.assert_violation(rc, err, self.REC)

    def test_divergent_push_direct_comparison_catches_rewrite(self) -> None:
        self.repo.write("sim/exp-a/records/r2.md", "r2\n")
        before = self.repo.commit("main: r2 (will be rewritten away)")
        # Force-push: new history branches from main1 and never had r2.
        self.repo.git("checkout", "-q", "-B", "main", self.main1)
        self.repo.write("docs/y.md", "y\n")
        after = self.repo.commit("rewritten main")
        rc, _, err = self.run_checker("--base", before, "--head", after)
        self.assert_violation(rc, err, "sim/exp-a/records/r2.md")
        # A merge-base comparison would have missed it -- which is why push CI
        # compares the prior SHA directly.
        rc, _, err = self.run_checker("--merge-base-of", before, "--head", after)
        self.assertEqual(rc, 0, err)


class PrecedenceAndFailureTest(GitTestCase):
    REC = "sim/exp-a/records/r1.md"

    def setUp(self) -> None:
        super().setUp()
        self.repo.write(self.REC, "r1\n")
        self.seeded = self.repo.commit("r1")
        self.repo.write(self.REC, "r1 edited\n")
        self.tampered = self.repo.commit("tamper")

    def test_env_base_and_head_used(self) -> None:
        env = {checker.ENV_BASE: self.seeded, checker.ENV_HEAD: self.tampered}
        rc, out, err = self.run_checker(env=env)
        self.assert_violation(rc, err, self.REC)
        self.assertIn(f"${checker.ENV_BASE}", out)

    def test_env_merge_base_of_used(self) -> None:
        env = {checker.ENV_MERGE_BASE_OF: self.seeded}
        rc, out, err = self.run_checker(env=env)
        self.assert_violation(rc, err, self.REC)
        self.assertIn(f"${checker.ENV_MERGE_BASE_OF}", out)

    def test_cli_overrides_env(self) -> None:
        env = {checker.ENV_BASE: self.seeded, checker.ENV_HEAD: self.tampered}
        # CLI base == head -> zero diff, despite the env asking for a failing range.
        rc, out, err = self.run_checker("--base", self.tampered, env=env)
        self.assertEqual(rc, 0, err)
        rc, out, err = self.run_checker(
            "--merge-base-of", self.tampered, "--head", self.tampered, env=env
        )
        self.assertEqual(rc, 0, err)
        # CLI --head alone overrides $APPEND_ONLY_HEAD but keeps the env base.
        rc, out, err = self.run_checker("--head", self.seeded, env=env)
        self.assertEqual(rc, 0, err)
        self.assertIn(f"head {self.seeded}", out)

    def test_empty_or_conflicting_env_fails(self) -> None:
        for env, needle in (
            ({checker.ENV_BASE: ""}, "set but empty"),
            ({checker.ENV_HEAD: " "}, "set but empty"),
            ({checker.ENV_MERGE_BASE_OF: ""}, "set but empty"),
            (
                {checker.ENV_BASE: self.seeded, checker.ENV_MERGE_BASE_OF: self.seeded},
                "set exactly one",
            ),
        ):
            with self.subTest(env):
                rc, _, err = self.run_checker(env=env)
                self.assert_cannot_compare(rc, err, needle)

    def test_base_and_merge_base_of_are_exclusive(self) -> None:
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self.run_checker("--base", self.seeded, "--merge-base-of", self.seeded)
        self.assertEqual(cm.exception.code, 2)

    def test_main_to_main_zero_diff(self) -> None:
        self.repo.git("update-ref", "refs/remotes/origin/main", self.tampered)
        rc, out, err = self.run_checker()
        self.assertEqual(rc, 0, err)
        self.assertIn("local default", out)
        self.assertIn("same commit -- zero diff", out)
        self.assertIn(f"base {self.tampered}", out)

    def test_local_default_compares_to_origin_main(self) -> None:
        self.repo.git("update-ref", "refs/remotes/origin/main", self.seeded)
        rc, out, err = self.run_checker()
        self.assert_violation(rc, err, self.REC)
        self.assertIn("merge-base of origin/main", out)

    def test_local_default_without_origin_main_fails(self) -> None:
        rc, _, err = self.run_checker()
        self.assert_cannot_compare(rc, err, "'origin/main' does not resolve")

    def test_absent_ref_fails(self) -> None:
        for argv, needle in (
            (["--base", "no-such-ref"], "base revision 'no-such-ref'"),
            (["--base", "deadbeef" * 5], "does not resolve"),
            (["--base", self.seeded, "--head", "nope"], "head revision 'nope'"),
            (["--merge-base-of", "nope"], "merge-base-of revision 'nope'"),
            (["--base=--all"], "looks like an option"),
        ):
            with self.subTest(argv):
                rc, _, err = self.run_checker(*argv)
                self.assert_cannot_compare(rc, err, needle)

    def test_all_zero_base_fails(self) -> None:
        rc, _, err = self.run_checker("--base", ZERO)
        self.assert_cannot_compare(rc, err, "all-zero SHA")
        rc, _, err = self.run_checker(env={checker.ENV_BASE: ZERO})
        self.assert_cannot_compare(rc, err, "all-zero SHA")

    def test_no_common_ancestor_fails(self) -> None:
        self.repo.git("checkout", "-q", "--orphan", "island")
        self.repo.write("other.txt", "o\n")
        self.repo.commit("orphan root")
        rc, _, err = self.run_checker("--merge-base-of", "main")
        self.assert_cannot_compare(rc, err, "no common ancestor")

    def test_shallow_clone_fails(self) -> None:
        clone = self.tmp / "shallow"
        subprocess.run(
            ["git", "clone", "-q", "--depth", "1",
             f"file://{self.repo.path}", str(clone)],
            check=True, capture_output=True,
        )
        rc, _, err = self.run_checker("--base", self.seeded, root=clone)
        self.assert_cannot_compare(rc, err, "shallow clone")
        rc, _, err = self.run_checker("--merge-base-of", "origin/main", root=clone)
        self.assert_cannot_compare(rc, err, "shallow clone")

    def test_git_failure_fails(self) -> None:
        not_a_repo = self.tmp / "plain"
        not_a_repo.mkdir()
        rc, _, err = self.run_checker("--base", "HEAD", root=not_a_repo)
        self.assert_cannot_compare(rc, err, "does not resolve")
        rc, _, err = self.run_checker("--base", "HEAD", root=self.tmp / "missing")
        self.assertEqual(rc, 2, err)

    def test_cli_entry_point_reads_process_environment(self) -> None:
        env = dict(os.environ)
        env[checker.ENV_BASE] = self.seeded
        proc = subprocess.run(
            [sys.executable, str(SIM_DIR / "check_append_only.py"),
             "--root", str(self.repo.path)],
            capture_output=True, text=True, env=env, check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn(repr(self.REC), proc.stderr)


if __name__ == "__main__":
    unittest.main()

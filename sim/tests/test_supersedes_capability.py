"""Unit tests for sim/check_supersedes_capability.py (issue #502: four
campaign runners could not express **Supersedes**, so a stale citation of their
records was undetectable by either citation gate).

No ngspice/PDK required -- pure AST/filesystem logic plus `--help` probes of
tiny synthetic runners, mirroring sim/tests/test_report.py's PDK-free
convention.

The important property under test is that the check is **fail-closed on a
synthetic tree**, not merely green on this repo's current one: a test that only
asserted "the real tree passes" would keep passing if the check's detection
logic were gutted. So every failure shape is reproduced against a throwaway
tree built here:

- a record-writing runner with no `--supersedes` flag at all (the gap #502 was
  filed for);
- a runner that declares `--supersedes` but drops it on ONE of its two write
  paths (issue #498's exact bug shape in run_transfer.py, which the gates could
  not see either);
- a runner whose prose help MENTIONS `--supersedes` without defining it (the
  false pass a naive grep of `--help` output would give -- and the shape this
  repo really had, since PR #503 wrote that mention into two runners' `--note`
  help text).

Plus: the real sim/ tree passes, and the explicit opt-out
(`evidence.NEVER_SUPERSEDES`) is accepted where a bare `""` is not.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

import check_supersedes_capability as checker  # noqa: E402

# A synthetic runner, parameterized by the argparse flags it declares and the
# `supersedes` argument each of its write paths passes. Imports nothing from
# the harness, so `--help` is instant and the fixture cannot drift with it.
RUNNER_TEMPLATE = '''\
"""Synthetic runner fixture."""
import argparse


class evidence:
    NEVER_SUPERSEDES = ""

    @staticmethod
    def footer_lines(written_by, supersedes):
        return []


def write_record({write_params}):
{write_bodies}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
{extra_flags}
    ap.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def make_tree(runners: dict[str, str]) -> tempfile.TemporaryDirectory:
    """A throwaway repo root containing `sim/<name>` for each given source."""
    tmp = tempfile.TemporaryDirectory(prefix="supersedes-capability-test-")
    sim = Path(tmp.name) / "sim"
    sim.mkdir()
    for rel, source in runners.items():
        path = sim / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return tmp


def runner_source(
    *, supersedes_flag: bool, write_args: list[str], note_help: str | None = None
) -> str:
    """Build a synthetic runner. `write_args` is one entry per write path,
    each the literal source of that path's `supersedes` argument."""
    bodies = "\n".join(
        f"    evidence.footer_lines(__file__, {arg})" for arg in write_args
    )
    flags = []
    if supersedes_flag:
        flags.append('    ap.add_argument("--supersedes", default="")')
    if note_help is not None:
        flags.append(f'    ap.add_argument("--note", default="", help={note_help!r})')
    return RUNNER_TEMPLATE.format(
        write_params='supersedes=""',
        write_bodies=bodies or "    pass",
        extra_flags="\n".join(flags) or "    pass",
    )


class TestRealTreePasses(unittest.TestCase):
    def test_this_repo_has_no_supersession_gaps(self):
        problems = checker.check(REPO_ROOT)
        self.assertEqual(
            [p.render() for p in problems],
            [],
            "sim/ has a record-writing path that cannot declare supersession",
        )

    def test_real_tree_actually_exercises_both_checks(self):
        """Guard against the test above passing vacuously: the real tree must
        contain record-writing runners AND footer_lines() call sites for the
        two checks to have anything to say."""
        self.assertGreater(len(checker.entry_points(REPO_ROOT)), 5)
        n_calls = sum(
            len(checker.footer_calls(p)) for p in checker.python_sources(REPO_ROOT)
        )
        self.assertGreater(n_calls, 5)


class TestMissingFlagFails(unittest.TestCase):
    def test_record_writer_without_supersedes_flag_is_reported(self):
        src = runner_source(supersedes_flag=False, write_args=['""'])
        with make_tree({"gap/run_gap.py": src}) as root:
            problems = checker.check(Path(root))
        kinds = sorted({p.kind for p in problems})
        self.assertIn("supersedes-flag-missing", kinds)
        self.assertIn("supersedes-dropped", kinds)

    def test_adding_the_flag_and_threading_it_passes(self):
        src = runner_source(supersedes_flag=True, write_args=["supersedes"])
        with make_tree({"ok/run_ok.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])


class TestSecondWritePathIsChecked(unittest.TestCase):
    """Issue #498's bug shape: the flag is declared and honoured on the first
    write path, and silently dropped on the second."""

    def test_flag_declared_but_dropped_on_one_path(self):
        src = runner_source(supersedes_flag=True, write_args=["supersedes", '""'])
        with make_tree({"partial/run_partial.py": src}) as root:
            problems = checker.check(Path(root))
        self.assertEqual([p.kind for p in problems], ["supersedes-dropped"])
        self.assertIn("bare literal", problems[0].detail)

    def test_both_paths_threaded_passes(self):
        src = runner_source(
            supersedes_flag=True, write_args=["supersedes", "supersedes"]
        )
        with make_tree({"both/run_both.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])


class TestExplicitOptOut(unittest.TestCase):
    def test_named_sentinel_is_accepted_where_bare_empty_is_not(self):
        bare = runner_source(supersedes_flag=True, write_args=['""'])
        named = runner_source(
            supersedes_flag=True, write_args=["evidence.NEVER_SUPERSEDES"]
        )
        with make_tree({"bare/run_bare.py": bare}) as root:
            self.assertEqual(
                [p.kind for p in checker.check(Path(root))], ["supersedes-dropped"]
            )
        with make_tree({"named/run_named.py": named}) as root:
            self.assertEqual(checker.check(Path(root)), [])


class TestHelpProseIsNotADefinition(unittest.TestCase):
    """The false pass a naive `'--supersedes' in help_text` test would give."""

    def test_flag_named_only_in_another_flags_help_is_not_accepted(self):
        src = runner_source(
            supersedes_flag=False,
            write_args=["evidence.NEVER_SUPERSEDES"],
            note_help=(
                "free-text note. This runner has no --supersedes, see #502, so a "
                "re-run cannot be traced back to what it replaced."
            ),
        )
        with make_tree({"prose/run_prose.py": src}) as root:
            problems = checker.check(Path(root))
        self.assertEqual([p.kind for p in problems], ["supersedes-flag-missing"])

    def test_usage_block_stops_at_the_first_blank_line(self):
        help_text = textwrap.dedent(
            """\
            usage: run_x.py [-h] [--record] [--note NOTE]

            options:
              --note NOTE    mentions --supersedes in prose only
            """
        )
        block = checker.usage_block(help_text)
        self.assertIn("--record", block)
        self.assertNotIn("--supersedes", block)
        self.assertTrue(checker.advertises(block, "--record"))
        self.assertFalse(checker.advertises(block, "--supersedes"))


class TestAdvertises(unittest.TestCase):
    def test_record_does_not_match_inside_ratified_record(self):
        block = "usage: run_x.py [-h] [--ratified-record]"
        self.assertFalse(checker.advertises(block, "--record"))
        self.assertTrue(checker.advertises(block, "--ratified-record"))

    def test_option_with_metavar_and_equals_is_matched(self):
        block = "usage: run_x.py [-h] [--supersedes SUPERSEDES]"
        self.assertTrue(checker.advertises(block, "--supersedes"))
        self.assertTrue(checker.advertises("usage: x [--supersedes=ID]", "--supersedes"))


class TestNonRecordWritersAreIgnored(unittest.TestCase):
    def test_runner_without_a_record_flag_needs_no_supersedes(self):
        src = RUNNER_TEMPLATE.format(
            write_params='supersedes=""',
            write_bodies="    pass",
            extra_flags="    pass",
        ).replace('ap.add_argument("--record", action="store_true")', "pass")
        with make_tree({"plain/run_plain.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])

    def test_script_without_argparse_is_not_probed(self):
        src = '#!/usr/bin/env python3\nif __name__ == "__main__":\n    pass\n'
        with make_tree({"gen/gen_thing.py": src}) as root:
            self.assertEqual(checker.entry_points(Path(root)), [])
            self.assertEqual(checker.check(Path(root)), [])


class TestFooterCallClassification(unittest.TestCase):
    def test_keyword_form_is_classified(self):
        with make_tree(
            {
                "kw/run_kw.py": (
                    "import argparse\n"
                    "def w():\n"
                    "    evidence.footer_lines(written_by=__file__, supersedes='')\n"
                    'if __name__ == "__main__":\n'
                    "    pass\n"
                )
            }
        ) as root:
            calls = checker.footer_calls(Path(root) / "sim" / "kw" / "run_kw.py")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].is_bare_empty)

    def test_fstring_literal_is_a_literal_but_not_empty(self):
        with make_tree(
            {
                "fs/run_fs.py": (
                    "OLD = 'x'\n"
                    "def w():\n"
                    "    evidence.footer_lines(__file__, f'records/{OLD}.md')\n"
                )
            }
        ) as root:
            calls = checker.footer_calls(Path(root) / "sim" / "fs" / "run_fs.py")
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0].is_bare_empty)
        self.assertTrue(calls[0].is_hardcoded_pointer)

    def test_docstring_mention_is_not_a_call_site(self):
        with make_tree(
            {"doc/run_doc.py": '"""calls footer_lines() somewhere else."""\n'}
        ) as root:
            calls = checker.footer_calls(Path(root) / "sim" / "doc" / "run_doc.py")
        self.assertEqual(calls, [])

    def test_tests_directory_is_excluded_from_the_scan(self):
        """This very file names footer_lines() in fixture source; the scan must
        not read it, or the suite would report itself."""
        scanned = checker.python_sources(REPO_ROOT)
        self.assertNotIn(Path(__file__).resolve(), scanned)


class TestHardcodedSupersessionIsExempt(unittest.TestCase):
    """A runner that hardcodes a narrative naming the specific record it
    displaces still populates **Supersedes**, so both citation gates can
    already see a stale citation of it -- the harm this check exists to
    prevent does not apply, and demanding a flag of it would be noise rather
    than a finding.

    Synthetic fixtures on purpose: the exemption's two original users
    (sim/sampling-acquisition-settling/ and sim/vcm-drive-budget/) retired
    from it in issue #513 by taking `--supersedes` with that narrative as the
    flag's default, so no real runner exercises this branch today."""

    def test_all_literal_write_paths_exempt_the_runner_from_the_flag(self):
        src = runner_source(
            supersedes_flag=False, write_args=["f'records/{OLD}.md -- same sweep'"]
        )
        src = "OLD = 'x'\n" + src
        with make_tree({"fixed/run_fixed.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])

    def test_one_non_literal_path_removes_the_exemption(self):
        src = runner_source(
            supersedes_flag=False,
            write_args=["f'records/{OLD}.md -- same sweep'", "supersedes"],
        )
        src = "OLD = 'x'\n" + src
        with make_tree({"mixed/run_mixed.py": src}) as root:
            problems = checker.check(Path(root))
        self.assertEqual([p.kind for p in problems], ["supersedes-flag-missing"])


class TestWriterCalledWithoutTheArgument(unittest.TestCase):
    """The third silent shape: the flag is declared, the writer forwards a
    name (so the threading check is satisfied), and main() still never passes
    it -- the record reads `(none)` however the runner was invoked."""

    WRITER = textwrap.dedent(
        '''\
        import argparse


        class evidence:
            @staticmethod
            def footer_lines(written_by, supersedes):
                return []


        def write_record(rows, supersedes=""):
            evidence.footer_lines(__file__, supersedes)


        def main():
            ap = argparse.ArgumentParser()
            ap.add_argument("--record", action="store_true")
            ap.add_argument("--supersedes", default="")
            args = ap.parse_args()
            write_record([]{call_tail})
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    )

    def test_omitted_keyword_is_reported(self):
        src = self.WRITER.format(call_tail="")
        with make_tree({"drop/run_drop.py": src}) as root:
            problems = checker.check(Path(root))
        self.assertEqual([p.kind for p in problems], ["supersedes-not-passed"])
        self.assertIn("write_record()", problems[0].detail)

    def test_supplied_keyword_passes(self):
        src = self.WRITER.format(call_tail=", supersedes=args.supersedes")
        with make_tree({"keep/run_keep.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])

    def test_supplied_positionally_passes(self):
        src = self.WRITER.format(call_tail=", args.supersedes")
        with make_tree({"pos/run_pos.py": src}) as root:
            self.assertEqual(checker.check(Path(root)), [])

    def test_every_real_runner_passes_it_at_every_call_site(self):
        for py_path in checker.python_sources(REPO_ROOT):
            with self.subTest(path=str(py_path.relative_to(REPO_ROOT))):
                self.assertEqual(checker.unthreaded_writers(py_path), [])


class TestRunnerProbeFailuresAreNotSilent(unittest.TestCase):
    def test_a_runner_whose_help_crashes_is_reported(self):
        src = (
            "import argparse\n"
            "raise SystemExit('boom')\n"
            "argparse.ArgumentParser()\n"
            'if __name__ == "__main__":\n'
            "    pass\n"
        )
        with make_tree({"broken/run_broken.py": src}) as root:
            problems = checker.check(Path(root))
        self.assertEqual([p.kind for p in problems], ["runner-help-failed"])


if __name__ == "__main__":
    unittest.main()

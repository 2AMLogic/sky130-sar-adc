"""`npm run check:ci` must run the `sim/tests` unit suite exactly once (issue
#889) -- pure stdlib, no PDK/ngspice/KLayout required, so it belongs to the
headless tier (same PDK-free unit-test convention as
sim/tests/test_layout_entrypoint_imports.py; see sim/selftest.sh stage 1/4).

These live under sim/tests/ because that is this repo's only unittest root,
not because the invariant belongs to the simulation harness -- it is a
property of `package.json`'s `check:ci` chain.

Why this exists
---------------
`check:ci` used to reach the suite twice in one invocation: through
`npm run test` -> `test:unit`, and again as `sim/selftest.sh`'s stage 1,
which is the same `unittest discover` over the same directory in the same
interpreter. Measured on CI run 43464556446 (`main`, green, 2026-11-13), the
"Repo checks (headless, no PDK)" job printed `Ran 1806 tests` twice, ~21 s
apiece. Issue #889 removed the first route: `check:ci` now runs
`npm run test:compile` and reaches the suite only through
`npm run check:harness` -> `sim/selftest.sh` stage 1.

Nothing structural stopped that duplication from arriving, and nothing would
stop it coming back -- re-adding `npm run test` to the chain, or adding a
`npm run test:unit` step beside `check:harness`, restores it silently, because
both runs pass. This module is that gate. It resolves the chain the way npm
does (expanding every `npm run <name>` reference against `scripts`) and counts
the terminal commands that run the suite, counting `sim/selftest.sh`'s own
stage 1 as one of them.

Two invariants it deliberately does NOT drop:

* The suite must still run at least once in `check:ci` -- a count of zero is
  as much a failure as a count of two.
* `sim/selftest.sh` must keep running it, because the `pdk-smoke` job calls
  `./sim/selftest.sh --require-pdk` directly rather than `check:ci`
  (`.github/workflows/ci.yml`), so stage 1 is that job's only unit-suite run
  and the only CI run of the suite on a machine that has ngspice -- which
  `sim/tests/test_top_plate_cpar.py`'s ngspice-gated class needs.

The counter is driven over a synthetic pre-#889 chain as a negative control,
so a counter that had stopped seeing either route could not report a vacuous
pass.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
PACKAGE_JSON = REPO_ROOT / "package.json"
SELFTEST_SH = SIM_DIR / "selftest.sh"

# The spelling every route to the suite shares: `python3 -m unittest discover`
# over sim/tests, whether written with `--start-directory` (package.json) or
# `-s` (sim/selftest.sh).
DISCOVER = "unittest discover"

_NPM_RUN = re.compile(r"^npm run ([A-Za-z0-9:._-]+)$")
# npm itself runs the body through a shell; only the separators that can
# introduce a *new* command need splitting for the purpose of spotting an
# `npm run <name>` reference.
_SEPARATORS = re.compile(r"&&|\|\||;")


def expand_script(name: str, scripts: dict[str, str]) -> list[str]:
    """Resolve `scripts[name]` into the terminal commands it runs.

    Every `npm run <other>` reference is replaced by that script's own
    expansion, which is what npm does at run time; anything else is a leaf.
    Self-reference cycles raise rather than recursing forever.
    """

    def walk(script: str, stack: tuple[str, ...]) -> list[str]:
        if script in stack:
            raise AssertionError(
                f"`npm run {script}` is cyclic: {' -> '.join(stack + (script,))}"
            )
        if script not in scripts:
            raise AssertionError(f"package.json has no script named {script!r}")
        leaves: list[str] = []
        for part in _SEPARATORS.split(scripts[script]):
            part = part.strip()
            if not part:
                continue
            referenced = _NPM_RUN.match(part)
            if referenced:
                leaves.extend(walk(referenced.group(1), stack + (script,)))
            else:
                leaves.append(part)
        return leaves

    return walk(name, ())


def count_unit_suite_runs(scripts: dict[str, str], selftest_text: str) -> int:
    """How many times `scripts['check:ci']` runs the sim/tests unit suite.

    A terminal command counts once per `unittest discover` it spells itself,
    plus -- when it invokes `sim/selftest.sh` -- once per `unittest discover`
    in that script, since npm cannot see inside it.
    """
    total = 0
    for leaf in expand_script("check:ci", scripts):
        total += leaf.count(DISCOVER)
        if "selftest.sh" in leaf:
            total += selftest_text.count(DISCOVER)
    return total


class TestCheckCiRunsTheUnitSuiteOnce(unittest.TestCase):
    def setUp(self) -> None:
        self.scripts = json.loads(PACKAGE_JSON.read_text())["scripts"]
        self.selftest_text = SELFTEST_SH.read_text()

    def test_the_unit_suite_runs_exactly_once_in_check_ci(self) -> None:
        self.assertEqual(
            count_unit_suite_runs(self.scripts, self.selftest_text),
            1,
            "`npm run check:ci` must discover sim/tests exactly once (issue "
            "#889). A count of 2 means a second route was re-added (most "
            "likely `npm run test` or `npm run test:unit` back in the chain "
            "beside `npm run check:harness`); a count of 0 means the suite "
            "stopped running on the PR-blocking path altogether.",
        )

    def test_selftest_still_runs_the_suite_for_pdk_smoke(self) -> None:
        self.assertEqual(
            self.selftest_text.count(DISCOVER),
            1,
            "sim/selftest.sh stage 1 must keep running the unit suite: the "
            "`pdk-smoke` job calls ./sim/selftest.sh --require-pdk directly, "
            "so it is that job's only unit-suite run and the only CI run of "
            "the suite on a machine with ngspice.",
        )

    def test_check_ci_reaches_the_suite_through_check_harness(self) -> None:
        """The route is selftest stage 1, not a direct `test:unit` step."""
        self.assertIn("npm run check:harness", self.scripts["check:ci"])
        self.assertNotIn("npm run test:unit", self.scripts["check:ci"])
        # `npm run test` expands to test:compile && test:unit, so it is the
        # other spelling that reintroduces the duplicate run.
        self.assertNotIn(
            "npm run test &&",
            self.scripts["check:ci"] + " &&",
        )

    def test_the_suite_runs_before_the_citation_gate(self) -> None:
        """Order the citation-gate evidence depends on (#889, #820).

        `sim/tests/test_proposal_citations.py` runs the proposal checks over
        the live tree, so it and `npm run check:proposal-citations` report the
        same stale citation. `docs/citation-gate-evidence.md` records that all
        99 observed CI fires surfaced through the unit-test step because the
        suite runs first; keeping that order keeps the finding reproducible,
        and keeps a broken checker diagnosed by its own unit tests rather than
        by a traceback from the script step.
        """
        chain = self.scripts["check:ci"]
        self.assertLess(
            chain.index("npm run check:harness"),
            chain.index("npm run check:proposal-citations"),
            "the unit suite (via check:harness) must run before "
            "check:proposal-citations",
        )

    def test_counter_sees_both_routes_of_the_pre_889_chain(self) -> None:
        """Negative control: the pre-#889 chain must count as 2."""
        pre_889 = dict(self.scripts)
        pre_889["check:ci"] = (
            "npm run lint && npm run test && npm run check:proposal-citations "
            "&& npm run check:harness && npm run check:report"
        )
        self.assertEqual(
            count_unit_suite_runs(pre_889, self.selftest_text),
            2,
        )

    def test_counter_sees_a_bare_discover_step_added_to_the_chain(self) -> None:
        """Negative control: a hand-written discover step also counts."""
        with_extra = dict(self.scripts)
        with_extra["check:ci"] = (
            self.scripts["check:ci"]
            + " && python3 -m unittest discover -s sim/tests -t sim/tests"
        )
        self.assertEqual(
            count_unit_suite_runs(with_extra, self.selftest_text),
            2,
        )

    def test_expand_script_rejects_a_cycle(self) -> None:
        with self.assertRaises(AssertionError):
            expand_script("check:ci", {"check:ci": "npm run check:ci"})

    def test_expand_script_rejects_an_undefined_reference(self) -> None:
        with self.assertRaises(AssertionError):
            expand_script("check:ci", {"check:ci": "npm run nope"})


if __name__ == "__main__":
    unittest.main()

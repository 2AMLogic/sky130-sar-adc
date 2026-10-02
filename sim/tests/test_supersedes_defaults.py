"""The two runners whose **Supersedes** narrative is a *default* rather than a
hardcoded constant (issue #513): sim/sampling-acquisition-settling/ and
sim/vcm-drive-budget/.

Both campaigns displaced one specific record once, in September 2026, and both
narrate that in prose their record's **Supersedes** field carries verbatim.
Issue #502 left them alone because they DO populate the field, so both citation
gates (`sim/report/generate.py --check`,
`docs/chipalooza/check_proposal_citations.py` check 3) can already see a stale
citation of them. The residual problem #513 closed is narrower: the pointer was
a fixed historical fact compiled into the runner, so the NEXT re-run would have
claimed to supersede the record *before* the one it actually displaces unless
somebody remembered to edit source mid-re-run.

What is asserted here is the half `npm run check:supersedes` cannot see. That
gate proves the flag exists and reaches `footer_lines()` on every write path
(AST + `--help`); it says nothing about *what each path falls back to* when the
flag is omitted. These tests pin that fallback: each default narrative names
that path's own displaced record, the four `--corners` narratives stay distinct
per `(--sweep, --window)`, and an explicit `--supersedes` value wins. No
ngspice/PDK: the narratives are pure text, same PDK-free convention
sim/tests/test_harness.py and sim/tests/test_run_hold_kick.py follow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(SIM_DIR / "sampling-acquisition-settling"))
sys.path.insert(0, str(SIM_DIR / "vcm-drive-budget"))

import run_acquisition_settling as acq  # noqa: E402
import run_vcm_drive_budget as vcm  # noqa: E402
from harness import evidence  # noqa: E402


def footer_supersedes(lines: list[str]) -> str:
    """The rendered `- **Supersedes**: …` field of an evidence footer."""
    prefix = "- **Supersedes**: "
    return next(ln[len(prefix):] for ln in lines if ln.startswith(prefix))


def resolve(flag: str, default: str) -> str:
    """The fallback every defaulted write path applies to its own argument:
    `supersedes = supersedes or <default narrative>`."""
    return flag or default


class TestAcquisitionSettlingDefaults(unittest.TestCase):
    def test_single_corner_default_names_its_own_displaced_record(self):
        narrative = acq.SINGLE_CORNER_SUPERSEDES_DEFAULT
        self.assertIn(acq.SINGLE_CORNER_SUPERSEDES_RECORD, narrative)
        self.assertIn("single tt/27C/1.8V point", narrative)

    def test_corners_default_names_its_own_displaced_record(self):
        narrative = acq.CORNERS_SUPERSEDES_DEFAULT
        self.assertIn(acq.CORNERS_SUPERSEDES_RECORD, narrative)
        self.assertIn("9-point", narrative)

    def test_the_two_defaults_are_not_the_same_narrative(self):
        """The two write paths displaced two different records; a copy-paste
        that pointed both at one of them would be invisible to the gate."""
        self.assertNotEqual(
            acq.SINGLE_CORNER_SUPERSEDES_DEFAULT, acq.CORNERS_SUPERSEDES_DEFAULT
        )


class TestVcmDriveBudgetDefaults(unittest.TestCase):
    def test_every_corners_combination_names_its_own_displaced_record(self):
        for (sweep, window), old_id in vcm.CORNERS_SUPERSEDES_RECORD.items():
            with self.subTest(sweep=sweep, window=window):
                narrative = vcm.default_corners_supersedes(sweep, window)
                self.assertIn(old_id, narrative)
                self.assertIn(f"at the {window} window", narrative)

    def test_the_four_corners_narratives_are_all_distinct(self):
        narratives = {
            vcm.default_corners_supersedes(sweep, window)
            for sweep, window in vcm.CORNERS_SUPERSEDES_RECORD
        }
        self.assertEqual(len(narratives), len(vcm.CORNERS_SUPERSEDES_RECORD))

    def test_rsource_and_decouple_narratives_describe_their_own_axis(self):
        self.assertIn(
            "bare (undecoupled) R_source sweep",
            vcm.default_corners_supersedes("rsource", "worst"),
        )
        self.assertIn(
            "C_decouple sweep", vcm.default_corners_supersedes("decouple", "worst")
        )

    def test_single_corner_default_names_the_seed_record(self):
        narrative = vcm.SINGLE_CORNER_SUPERSEDES_DEFAULT
        self.assertIn(vcm.SINGLE_CORNER_SEED_RECORD, narrative)

    def test_single_corner_default_does_not_call_issue_248_outstanding(self):
        """Issue #248 (re-deriving the four `--corners` records against the
        post-#236 DUT) closed 2026-09-08, and each of those four records is
        superseded by its own post-#236 re-run. The narrative must not still
        describe that work as pending -- it was checked against the tracker
        when #513 was implemented."""
        narrative = vcm.SINGLE_CORNER_SUPERSEDES_DEFAULT
        self.assertNotIn("not-yet-done", narrative)
        self.assertIn("issue #248, since done", narrative)
        for superseding_id in (
            "20260908-100413-f3e2914",
            "20260908-101358-f3e2914",
            "20260908-113002-f3e2914",
            "20260908-115336-f3e2914",
        ):
            self.assertIn(superseding_id, narrative)


class TestExplicitFlagWins(unittest.TestCase):
    """The point of the flag: a re-run names what it actually displaces, and
    nothing of the compiled-in default survives into the record."""

    EXPLICIT = "[`records/29990101-000000-deadbee.md`](29990101-000000-deadbee.md) -- a later re-run"

    def test_explicit_value_replaces_the_acquisition_defaults(self):
        for default in (
            acq.SINGLE_CORNER_SUPERSEDES_DEFAULT,
            acq.CORNERS_SUPERSEDES_DEFAULT,
        ):
            with self.subTest(default=default[:40]):
                rendered = footer_supersedes(
                    evidence.footer_lines(
                        "sim/x/run_x.py", resolve(self.EXPLICIT, default)
                    )
                )
                self.assertEqual(rendered, self.EXPLICIT)
                self.assertNotIn("pre-issue-#236", rendered)

    def test_omitted_flag_renders_the_default_not_none(self):
        """The fallback is `supersedes or <default>`, so an omitted flag must
        never reach the footer as the empty string that renders `(none)` --
        that would silently drop the supersession these records have always
        declared."""
        for default in (
            acq.SINGLE_CORNER_SUPERSEDES_DEFAULT,
            acq.CORNERS_SUPERSEDES_DEFAULT,
            vcm.SINGLE_CORNER_SUPERSEDES_DEFAULT,
            vcm.default_corners_supersedes("rsource", "worst"),
        ):
            with self.subTest(default=default[:40]):
                rendered = footer_supersedes(
                    evidence.footer_lines("sim/x/run_x.py", resolve("", default))
                )
                self.assertEqual(rendered, default)
                self.assertNotEqual(rendered, "(none)")


class TestFlagHelpTextIsAccurateForADefaultedPath(unittest.TestCase):
    """`SUPERSEDES_ARG_HELP`'s last sentence ("the footer then reads
    `(none)`") is true of the eight runners issue #502 standardized and FALSE
    of these two, where omitting the flag re-states a historical narrative.
    `extra_help` is how a defaulted runner says so in its own `--help`."""

    def test_extra_help_is_appended_to_the_shared_text(self):
        import argparse

        parser = argparse.ArgumentParser()
        evidence.add_supersedes_argument(parser, extra_help="Omitting it writes X.")
        action = next(a for a in parser._actions if a.dest == "supersedes")
        self.assertTrue(action.help.startswith(evidence.SUPERSEDES_ARG_HELP))
        self.assertTrue(action.help.endswith("Omitting it writes X."))
        self.assertEqual(action.default, "")

    def test_shared_text_is_unchanged_when_extra_help_is_omitted(self):
        import argparse

        parser = argparse.ArgumentParser()
        evidence.add_supersedes_argument(parser)
        action = next(a for a in parser._actions if a.dest == "supersedes")
        self.assertEqual(action.help, evidence.SUPERSEDES_ARG_HELP)


if __name__ == "__main__":
    unittest.main()

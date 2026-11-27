"""Unit test for sim/cdac-array-transfer/run_mc.py's `reanalyze_from_logs()`
(issue #129) -- pure log re-parsing, NO ngspice/PDK required (mirrors
sim/tests/test_harness.py's PDK-free unit-test convention; see
sim/selftest.sh stage 1/4).

`reanalyze_from_logs()` re-derives DNL/INL statistics from a PRIOR record's
already-committed `mc-draws/<record-id>/*.log` files without re-running
ngspice -- this is the mechanism DR-007 (issue #129) uses to evidence a
candidate revised INL/DNL target against the SAME draws issue #29 already
collected. This test asserts the reanalysis reproduces issue #29's own
committed record (`sim/cdac-array-transfer/records/20260828-005006-0c70212.md`)
exactly: a divergence here would mean the reanalysis path silently computes
different numbers than the original run, undermining DR-007's evidence."""

from __future__ import annotations

import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SIM_DIR = Path(__file__).resolve().parent.parent
CDAC_DIR = SIM_DIR / "cdac-array-transfer"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(CDAC_DIR))

import run_mc  # noqa: E402
from analysis import attribute_1016 as study  # noqa: E402
from run_mc import (  # noqa: E402
    DRAFT_INL_DNL_TARGET_LSB,
    reanalysis_prose_line,
    reanalyze_from_logs,
    target_provenance_prose,
)

SOURCE_RECORD_ID = "20260828-005006-0c70212"
PILOT_RECORD_ID = "20261121-075027-75b91e85"


class TestReanalyzeFromLogs(unittest.TestCase):
    def setUp(self):
        draws_dir = CDAC_DIR / "mc-draws" / SOURCE_RECORD_ID
        if not draws_dir.is_dir():
            self.skipTest(f"source mc-draws directory not present: {draws_dir}")

    def test_reproduces_issue_29_recorded_statistics(self):
        result = reanalyze_from_logs(SOURCE_RECORD_ID)
        self.assertEqual(result.n, 40)
        self.assertEqual(result.source_record_id, SOURCE_RECORD_ID)
        self.assertEqual(result.mismatch_corner, "tt_mm")

        dnl = [d.dnl_max_lsb for d in result.draws]
        inl = [d.inl_max_lsb for d in result.draws]

        # From sim/cdac-array-transfer/records/20260828-005006-0c70212.md's
        # own "DNL/INL distributions" table (mean/stdev/min/max, 4 s.f.).
        self.assertAlmostEqual(statistics.fmean(dnl), 0.7833, places=4)
        self.assertAlmostEqual(statistics.pstdev(dnl), 0.3083, places=4)
        self.assertAlmostEqual(min(dnl), 0.3275, places=4)
        self.assertAlmostEqual(max(dnl), 1.9716, places=4)

        self.assertAlmostEqual(statistics.fmean(inl), 0.7191, places=4)
        self.assertAlmostEqual(statistics.pstdev(inl), 0.2058, places=4)
        self.assertAlmostEqual(min(inl), 0.3818, places=4)
        self.assertAlmostEqual(max(inl), 1.3147, places=4)

    def test_negative_control_reproduces_zero_spread(self):
        result = reanalyze_from_logs(SOURCE_RECORD_ID)
        dnl_neg = [d.dnl_max_lsb for d in result.negctrl]
        inl_neg = [d.inl_max_lsb for d in result.negctrl]
        self.assertEqual(statistics.pstdev(dnl_neg), 0.0)
        self.assertEqual(statistics.pstdev(inl_neg), 0.0)

    def test_missing_source_record_raises(self):
        with self.assertRaises(FileNotFoundError):
            reanalyze_from_logs("no-such-record-id")


class TestEvidenceProvenance(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.experiment = Path(temp.name)
        for name in ("mc-draws", "records", "netlist-snapshots"):
            (self.experiment / name).mkdir()
        for record in (SOURCE_RECORD_ID, PILOT_RECORD_ID):
            for path in (Path("mc-draws", record), Path("records", record + ".md"),
                         Path("netlist-snapshots", record + ".spice")):
                (self.experiment / path).symlink_to(CDAC_DIR / path)
        self.enterContext(patch.object(run_mc, "EXPERIMENT_DIR", self.experiment))

    def replay(self, source, *args):
        with patch.object(sys, "argv", ["run_mc", "--reanalyze", source, "--record", "--quiet", *args]):
            return run_mc.main()

    def test_default_replay_copies_candidate_and_legacy_decks(self):
        for source, side in ((PILOT_RECORD_ID, "3.3000"), (SOURCE_RECORD_ID, "1.8988")):
            with self.subTest(source=source), patch.object(run_mc.evidence, "new_record_id", return_value=source + "-replay"):
                with patch.object(run_mc.evidence, "run_klt_yield", return_value=None) as report:
                    self.assertEqual(self.replay(source, "--negative-control-record", SOURCE_RECORD_ID), 0)
                for measurement in report.call_args.args[0]:
                    self.assertEqual(len(measurement["negative_control"]["samples"]), 40)
                decks = self.experiment / "netlist-snapshots"
                self.assertEqual((decks / (source + "-replay.spice")).read_bytes(),
                                 (decks / (source + ".spice")).read_bytes())
                record = (self.experiment / "records" / (source + "-replay.md")).read_text()
                self.assertIn(f"W = L = {side} um", record)
                self.assertIn(f"The {side} um plate was sampled at this PVT point only", record)
                if source == PILOT_RECORD_ID:
                    self.assertIn("nominal C = 23.805 fF", record)
                    self.assertIn("0.1362%", record)
                    self.assertIn("remain unmeasured for that geometry", record)

    def test_fresh_candidate_claim_identifies_simulated_dut_and_target(self):
        result = reanalyze_from_logs(PILOT_RECORD_ID)
        result.source_record_id = None
        with patch.object(run_mc.evidence, "run_klt_yield", return_value={"measurements": []}):
            path, ok = run_mc.write_evidence(result)
        self.assertTrue(ok)
        claim = next(line for line in path.read_text().splitlines() if line.startswith("- **Claim**"))
        self.assertIn("generated CDAC study variant with 3.3000 um square unit plates", claim)
        self.assertIn("original DRAFT INL/DNL limit (±1 LSB)", claim)
        self.assertIn("#1016", claim)

    def test_rejected_requests_leave_no_artifacts(self):
        original = set(self.experiment.rglob("*"))
        for args, error, message in (
            (("--unit-cap-side-um", "1.9"), ValueError, "conflicts with simulated plate"),
            (("--negative-control-record", "unavailable"), FileNotFoundError, "unavailable"),
            (("--gain-error",), ValueError, "DR-019 plate"),
            (("--gain-error", "--unit-cap-side-um", "3.3"), ValueError, "DR-019 plate"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(error, message):
                    self.replay(PILOT_RECORD_ID, *args)
                self.assertEqual(set(self.experiment.rglob("*")), original)


class TestCapsOnlyProbe(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.experiment = Path(temp.name)
        self.analysis = self.experiment / "analysis"
        self.probe = self.analysis / study.PROBE_DIR_NAME
        self.probe.mkdir(parents=True)
        for log in (CDAC_DIR / "analysis" / study.PROBE_DIR_NAME).glob("*.log"):
            shutil.copy(log, self.probe / log.name)
        self.enterContext(patch.object(study, "EXPERIMENT_DIR", self.experiment))
        self.enterContext(patch.object(sys, "argv", ["attribute_1016.py", "--record"]))

    def test_later_probe_does_not_change_the_study(self):
        later = self.analysis / "probe-caps-only-99999999"
        later.mkdir()
        shutil.copy(self.probe / "capsonly_seed1.log", later)
        self.assertEqual(study.main(), 0)
        (record,) = self.analysis.glob("*.md")
        report = record.read_text()
        self.assertIn(f"`{self.probe.name}/` (caps-only isolation probe, N=8, seeds 1..8)", report)
        self.assertIn("| 255 | 1596.7 | 1459.8 |", report)
        self.assertNotIn(later.name, report)

    def test_invalid_probe_cannot_mint_a_record(self):
        log = self.probe / "capsonly_seed1.log"
        original = log.read_text()
        for bad_log in (None, "", original.replace("seed=1 ", "seed=2 "),
                        re.sub(r"^vtop_p_0 .*", "", original, flags=re.M),
                        re.sub(r"^vtop_n_511 .*", "vtop_n_511 = 1e999", original, flags=re.M)):
            with self.subTest(case=None if bad_log is None else len(bad_log)):
                if bad_log is None:
                    log.unlink()
                else:
                    log.write_text(bad_log)
                with self.assertRaises(SystemExit) as failure:
                    study.main()
                self.assertEqual(failure.exception.code, 2)
                self.assertEqual(list(self.analysis.glob("*.md")), [])


class TestPilotSizing(unittest.TestCase):
    def test_reported_bounds_on_committed_draws(self):
        output = subprocess.check_output(
            [sys.executable, str(CDAC_DIR / "analysis" / "attribute_1016.py")], text=True
        )
        self.assertIn("option A minimum plate (both margins met): 3.195 um", output)
        self.assertRegex(output, r"all-40-draws-pass bound .*: 4\.510 um")
        self.assertIn("effective fit coefficient: 1.9475%", output)
        self.assertIn("effective fit coefficient: 2.3192%", output)
        self.assertIn("Combined tt_mm sigma at 1.9000 um: 0.2293 %", output)
        self.assertIn("candidate fitted bounds: DNL 0.976534 LSB", output)
        self.assertIn("option B t=1: dnl yield 0.825 margin -0.509", output)
        self.assertIn("option B t=2: dnl yield 0.975 margin -0.116", output)
        self.assertIn("option B t=3: dnl yield 0.975 margin +0.141", output)
        self.assertIn("option D t=2: plate 2.370 area x1.56 dnl yield 0.975", output)
        self.assertIn("option D t=3: plate 2.370 area x1.56 dnl yield 1.000", output)
        for option, spreads in (("B", ("0.3120/0.2085", "0.2290/0.2085", "0.1755/0.2085")),
                                ("D", ("0.1953/0.1721", "0.1494/0.1721"))):
            lines = [line for line in output.splitlines() if line.startswith(f"option {option} t=")]
            self.assertEqual([line.split("DNL/INL sd ")[1] for line in lines],
                             [f"{pair} LSB" for pair in spreads])

    def test_stdev_precision_at_pilot_and_target_boundary(self):
        for n, expected in (
            (1, "too small"),
            (16, "18.3%, exceeding"),
            (50, "10.1%, exceeding"),
            (51, "10.0%, meeting"),
            (52, "9.9%, meeting"),
        ):
            with self.subTest(n=n):
                self.assertIn(expected, run_mc.stdev_precision_prose(n))


class TestTargetProvenanceProse(unittest.TestCase):
    """The target-provenance prose is keyed on the LIMIT actually used, not
    on whether the run is a reanalysis (issue #912): at the DRAFT
    target-spec row's limit (1.0 LSB) the record must name
    `spec/target-spec.md`'s DRAFT row -- DR-007 proposes 2.0 LSB, so
    labelling a 1.0 LSB evaluation as DR-007's proposal would put a false
    provenance claim about a spec target into an append-only record."""

    def test_draft_limit_names_target_spec_row_not_dr007(self):
        provenance = target_provenance_prose(DRAFT_INL_DNL_TARGET_LSB, 0.99)
        claim = provenance.claim_body
        target_desc = provenance.target_desc
        self.assertIn("1 LSB", claim)
        self.assertIn("spec/target-spec.md", claim)
        self.assertIn("DRAFT", claim)
        self.assertNotIn("CANDIDATE REVISED", claim)
        self.assertNotIn("DR-007", claim)
        self.assertIn("spec/target-spec.md", target_desc)
        self.assertIn("DRAFT", target_desc)
        self.assertNotIn("CANDIDATE REVISED", target_desc)
        self.assertNotIn("DR-007", target_desc)

    def test_non_draft_limit_still_names_dr007(self):
        provenance = target_provenance_prose(2.0, 0.99)
        claim = provenance.claim_body
        target_desc = provenance.target_desc
        self.assertIn("CANDIDATE REVISED", claim)
        self.assertIn("DR-007", claim)
        self.assertIn("2 LSB", claim)
        self.assertIn("CANDIDATE REVISED", target_desc)
        self.assertIn("DR-007", target_desc)
        self.assertIn("2 LSB", target_desc)
        self.assertNotIn("DRAFT (not ratified) INL/DNL target row", target_desc)

    def test_draft_limit_is_exactly_the_constant(self):
        # The DRAFT branch must trigger on the constant itself (the CLI
        # default), so the mint at AC5's limit cannot drift into the DR-007
        # branch through a float-typo'd default.
        provenance = target_provenance_prose(DRAFT_INL_DNL_TARGET_LSB, 0.99)
        self.assertNotIn("DR-007", provenance.claim_body)
        self.assertEqual(DRAFT_INL_DNL_TARGET_LSB, 1.0)


class TestFreshClaimProse(unittest.TestCase):
    """Mirror of TestTargetProvenanceProse for the FRESH (non-reanalysis)
    branch's Claim bullet (issue #948): that branch previously hardcoded the
    DRAFT row's `<= +-1 LSB` limit, so a fresh `--record
    --target-limit-lsb 2.0` run would mint a record whose Claim names the
    DRAFT row while its own yield-evidence sentence names DR-007's CANDIDATE
    REVISED proposal -- a self-contradicting provenance claim in an
    append-only record. Guards are case-insensitive, per the
    TestReanalysisProseLine docstring's stated reason (a case-sensitive
    grep missed the #912 defect)."""

    def test_draft_limit_names_target_spec_row_not_dr007(self):
        provenance = target_provenance_prose(DRAFT_INL_DNL_TARGET_LSB, 0.99)
        body = provenance.fresh_claim_body
        self.assertIn("1 LSB", body)
        self.assertIn("spec/target-spec.md", body)
        self.assertIn("DRAFT", body)
        lowered = body.lower()
        self.assertNotIn("candidate revised", lowered)
        self.assertNotIn("dr-007", lowered)

    def test_non_draft_limit_names_dr007_not_draft_row(self):
        provenance = target_provenance_prose(2.0, 0.99)
        body = provenance.fresh_claim_body
        self.assertIn("CANDIDATE REVISED", body)
        self.assertIn("DR-007", body)
        self.assertIn("2 LSB", body)
        lowered = body.lower()
        self.assertNotIn("1 lsb", lowered)
        self.assertNotIn("draft", lowered)
        self.assertNotIn("spec/target-spec.md", lowered)

    def test_claim_and_yield_sentence_agree_at_both_limits(self):
        # The invariant whose violation IS this issue: a fresh record's
        # Claim bullet and its own "Against {target_desc}, ..." sentence
        # must name the SAME target source and the SAME limit.
        for limit in (DRAFT_INL_DNL_TARGET_LSB, 2.0):
            provenance = target_provenance_prose(limit, 0.99)
            body = provenance.fresh_claim_body.lower()
            desc = provenance.target_desc.lower()
            limit_str = f"{limit:g} lsb"
            self.assertIn(limit_str, body, f"limit {limit}: body")
            self.assertIn(limit_str, desc, f"limit {limit}: desc")
            is_draft = limit == DRAFT_INL_DNL_TARGET_LSB
            source_terms = (
                ("spec/target-spec.md", "draft")
                if is_draft
                else ("dr-007", "candidate revised")
            )
            other_terms = (
                ("dr-007", "candidate revised")
                if is_draft
                else ("spec/target-spec.md", "draft")
            )
            for term in source_terms:
                self.assertIn(term, body, f"limit {limit}: body {term!r}")
                self.assertIn(term, desc, f"limit {limit}: desc {term!r}")
            for term in other_terms:
                self.assertNotIn(term, body, f"limit {limit}: body {term!r}")
                self.assertNotIn(term, desc, f"limit {limit}: desc {term!r}")

    def test_archived_and_fresh_targets_name_the_original_limit(self):
        provenance = target_provenance_prose(DRAFT_INL_DNL_TARGET_LSB, 0.99)
        for text in (provenance.claim_body, provenance.fresh_claim_body, provenance.target_desc):
            self.assertIn("original DRAFT INL/DNL limit (±1 LSB)", text)
            self.assertIn("#1016", text)
            self.assertIn("earlier value", text)

    def test_explicit_default_float_takes_draft_branch(self):
        # A float equal-but-not-identical to the constant (e.g. from
        # float("1.0")) must still take the DRAFT branch.
        provenance = target_provenance_prose(float("1.0"), 0.99)
        lowered = provenance.fresh_claim_body.lower()
        self.assertIn("draft", lowered)
        self.assertNotIn("dr-007", lowered)
        self.assertNotIn("candidate revised", lowered)

    def test_intermediate_limit_names_the_requested_value(self):
        provenance = target_provenance_prose(1.5, 0.99)
        for text in provenance:
            self.assertIn("user-specified INL/DNL study limit (±1.5 LSB)", text)
            self.assertNotIn("DR-007", text)


class TestReanalysisProseLine(unittest.TestCase):
    """The reanalysis bullet is a mechanism description shared by every
    reanalysis mint, so it must be limit-NEUTRAL -- the **Claim** bullet
    directly above it carries the limit-keyed provenance. The pre-#912 text
    hardcoded "the candidate revised limit", which at the DRAFT 1.0 LSB
    default made the record assert (in prose, two lines below a correct
    Claim) that the run was scored against DR-007's candidate; a
    case-SENSITIVE grep for the uppercase constants missed it (issue #912
    review). These guards are case-insensitive for exactly that reason."""

    def test_is_limit_neutral(self):
        line = reanalysis_prose_line("20261001-124049-5207381")
        self.assertIn("against the target limit named above", line)
        lowered = line.lower()
        self.assertNotIn("candidate revised", lowered)
        self.assertNotIn("dr-007", lowered)

    def test_names_the_source_record(self):
        line = reanalysis_prose_line("20261001-124049-5207381")
        self.assertIn("`mc-draws/20261001-124049-5207381/`", line)
        self.assertIn(
            "`sim/cdac-array-transfer/records/20261001-124049-5207381.md`", line
        )
        self.assertIn("NO new ngspice invocation", line)


class TestKltEnvProse(unittest.TestCase):
    """klt_env_prose() must never raise and must always say something honest
    about the klt it found (or did not find); when a klt with the yield pair
    IS on PATH it names all three versions."""

    def test_never_raises_and_names_klt(self):
        prose = run_mc.klt_env_prose()
        self.assertTrue(prose)
        self.assertIn("klt", prose)

    def test_names_yield_pair_when_available(self):
        if shutil.which("klt") is None:
            self.skipTest("no klt on PATH")
        prose = run_mc.klt_env_prose()
        self.assertIn("klt yield envelope", prose)


if __name__ == "__main__":
    unittest.main()

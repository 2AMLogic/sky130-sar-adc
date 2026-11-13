"""Unit tests for sim/report/plots.py (issue #835: summary plots).

No matplotlib, no ngspice, no PDK -- the module under test is deliberately
split so the gate half is stdlib-only (see that module's docstring), and these
tests exercise exactly that half:

* `hash_problems()` against a SYNTHETIC fixture tree, so a failure mode is
  proven by constructing it rather than by hoping this repository happens to
  be stale today. Every parameter the gate reads (repo root, plots directory,
  renderer path, plot set) is injected, so the fixture is self-contained.
* the stdlib record/log parsers against hand-built inputs, including the
  escaped-pipe table shape `sim/` records actually contain.
* the committed `docs/plots/manifest.json` itself, as a regression test that
  `test:unit` catches plot drift the same way `npm run check:report` does.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))

from report import plots  # noqa: E402


FIXTURE_SPEC = plots.PlotSpec(
    key="fixture-plot",
    spec_row="enob",
    title="fixture",
    what="a synthetic figure, for the gate's own tests",
    source_record="sim/fixture/records/20260101-000000-abcdef1.md",
    extra_inputs=("sim/fixture/corners/20260101-000000-abcdef1/tt_27c_1.80v.log",),
)
FIXTURE_SPECS = (FIXTURE_SPEC,)


class FixtureTree:
    """A throwaway repo-shaped tree with one plot, rendered and manifested.

    Built by hand rather than by calling `render_all()` so these tests need no
    matplotlib: the "SVG" is just bytes the gate hashes, which is all the hash
    half of the gate ever looks at.
    """

    def __init__(self, root: Path):
        self.root = root
        self.plots_dir = root / "docs" / "plots"
        self.plots_dir.mkdir(parents=True)
        self.script = root / "renderer.py"
        self.script.write_text("# pretend renderer\n")

        self.inputs = {}
        for rel in FIXTURE_SPEC.inputs:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"evidence bytes for {rel}\n")
            self.inputs[rel] = path

        self.svg = root / FIXTURE_SPEC.rel_output
        self.svg.write_text("<svg>fixture</svg>\n")
        self.write_manifest()

    def write_manifest(self, **overrides) -> None:
        document = {
            "schema_version": plots.MANIFEST_SCHEMA_VERSION,
            "note": "fixture",
            "generator": plots.SCRIPT_REL,
            "generator_sha256": plots.sha256_bytes_file(self.script),
            "plots": {
                FIXTURE_SPEC.key: {
                    "file": FIXTURE_SPEC.rel_output,
                    "title": FIXTURE_SPEC.title,
                    "what": FIXTURE_SPEC.what,
                    "spec_row": FIXTURE_SPEC.spec_row,
                    "spec_row_label": "ENOB — DRAFT (target value)",
                    "source_record": FIXTURE_SPEC.source_record,
                    "source_record_id": "20260101-000000-abcdef1",
                    "output_sha256": plots.sha256_bytes_file(self.svg),
                    "inputs": {
                        rel: plots.sha256_bytes_file(path)
                        for rel, path in self.inputs.items()
                    },
                }
            },
        }
        document.update(overrides)
        (self.plots_dir / "manifest.json").write_text(json.dumps(document, indent=2) + "\n")

    def problems(self) -> list[str]:
        return plots.hash_problems(
            FIXTURE_SPECS, self.root, self.plots_dir, self.script
        )


class TestHashGateOnFixture(unittest.TestCase):
    """The four staleness modes the issue names, each constructed on purpose."""

    def _tree_at(self, tmp: str) -> FixtureTree:
        return FixtureTree(Path(tmp))

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._tree_at(tmp).problems(), [])

    def test_edited_evidence_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            rel = FIXTURE_SPEC.source_record
            tree.inputs[rel].write_text("evidence bytes, but one byte different\n")
            problems = tree.problems()
            self.assertTrue(problems, "an edited evidence input must fail the gate")
            self.assertTrue(
                any(rel in p and "changed since" in p for p in problems),
                f"the failure must name the changed input: {problems}",
            )

    def test_edited_svg_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.svg.write_text("<svg>hand-edited</svg>\n")
            problems = tree.problems()
            self.assertTrue(
                any("has been edited since it was rendered" in p for p in problems),
                f"a hand-edited figure must fail the gate: {problems}",
            )

    def test_svg_with_no_manifest_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            (tree.plots_dir / "stray.svg").write_text("<svg>stray</svg>\n")
            problems = tree.problems()
            self.assertTrue(
                any("stray.svg" in p and "ungated figure" in p for p in problems),
                f"an unclaimed SVG must fail the gate: {problems}",
            )

    def test_manifest_entry_with_no_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.svg.unlink()
            problems = tree.problems()
            self.assertTrue(
                any("does not exist" in p for p in problems),
                f"a manifest entry with no file must fail the gate: {problems}",
            )

    def test_changed_renderer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.script.write_text("# pretend renderer, edited\n")
            problems = tree.problems()
            self.assertTrue(
                any("has changed since the plots were rendered" in p for p in problems),
                f"an edited renderer must fail the gate: {problems}",
            )

    def test_missing_evidence_input_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.inputs[FIXTURE_SPEC.source_record].unlink()
            problems = tree.problems()
            self.assertTrue(
                any("no longer exists" in p for p in problems),
                f"a vanished evidence input must fail the gate: {problems}",
            )

    def test_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            (tree.plots_dir / "manifest.json").unlink()
            self.assertTrue(
                any("does not exist" in p for p in tree.problems()),
                "a missing manifest must fail the gate",
            )

    def test_plot_defined_but_not_manifested_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.write_manifest(plots={})
            problems = tree.problems()
            self.assertTrue(
                any("absent from" in p for p in problems),
                f"a plot the renderer defines must be in the manifest: {problems}",
            )

    def test_orphaned_manifest_entry_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            problems = plots.hash_problems((), tree.root, tree.plots_dir, tree.script)
            self.assertTrue(
                any("no longer defines" in p for p in problems),
                f"a manifest entry with no PlotSpec must fail the gate: {problems}",
            )

    def test_wrong_schema_version_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            tree.write_manifest(schema_version=plots.MANIFEST_SCHEMA_VERSION + 1)
            self.assertTrue(
                any("schema_version" in p for p in tree.problems()),
                "an unknown manifest schema version must fail the gate",
            )

    def test_unparseable_manifest_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._tree_at(tmp)
            (tree.plots_dir / "manifest.json").write_text("{not json")
            self.assertTrue(
                any("not valid JSON" in p for p in tree.problems()),
                "a corrupt manifest must fail the gate",
            )


class TestRecordParsers(unittest.TestCase):
    """The stdlib parsers the loaders are built on."""

    def test_split_row_honours_escaped_pipes(self):
        # The shape sim/cdac-array-transfer's Monte Carlo record actually has:
        # a leading cell containing escaped pipes. A naive split("|") tears it
        # into three cells and silently shifts every column after it.
        cells = plots._split_row(r"| max\|DNL\| | 40 | 0.7828 | 0.3080 |")
        self.assertEqual(cells, ["max|DNL|", "40", "0.7828", "0.3080"])

    def test_markdown_table_selects_by_header_and_stops_at_the_end(self):
        text = (
            "intro\n\n"
            "| statistic | N |\n|---|---|\n| max\\|INL\\| | 40 |\n\n"
            "after\n\n"
            "| corner | gap |\n|---|---|\n| `tt` | 0.9 |\n"
        )
        self.assertEqual(plots._markdown_table(text, "statistic"), [["max|INL|", "40"]])
        self.assertEqual(plots._markdown_table(text, "corner"), [["`tt`", "0.9"]])

    def test_record_field_accepts_a_parenthetical_qualifier(self):
        # `- **Measured value(s)** (`tt_27c_1.80v`): ...` -- the qualifier sits
        # OUTSIDE the bold span, before the colon.
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "r.md"
            record.write_text(
                "- **Record ID**: 20260101-000000-abcdef1\n"
                "- **Measured value(s)** (`tt_27c_1.80v`): SNDR = **52.00 dB**\n"
            )
            self.assertEqual(
                plots._record_field(record, "Record ID"), "20260101-000000-abcdef1"
            )
            self.assertEqual(
                plots._record_field(record, "Measured value(s)"),
                "SNDR = **52.00 dB**",
            )
            self.assertIsNone(plots._record_field(record, "Overall"))

    def test_measures_reads_ngspice_meas_lines_and_skips_the_rest(self):
        log = (
            " Reference value :  2.00000e-11\n"
            "vtop_p_0            =  9.00000e-01\n"
            "vtop_n_0            =  2.69716e+00\n"
            "failed_meas         =  failed\n"
        )
        self.assertEqual(
            plots._measures(log), {"vtop_p_0": 0.9, "vtop_n_0": 2.69716}
        )

    def test_agree_raises_on_a_mismatch_and_is_silent_on_a_match(self):
        plots._agree("x", 1.0, 1.0, tolerance=0.0, where="fixture")
        with self.assertRaises(plots.ProvenanceError):
            plots._agree("x", 1.0, 1.5, tolerance=0.01, where="fixture")

    def test_superseding_sibling_finds_a_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "records"
            records.mkdir()
            old = records / "20260101-000000-aaaaaaa.md"
            old.write_text("- **Record ID**: 20260101-000000-aaaaaaa\n")
            self.assertIsNone(plots._superseding_sibling(old))
            new = records / "20260202-000000-bbbbbbb.md"
            new.write_text(
                "- **Record ID**: 20260202-000000-bbbbbbb\n"
                "- **Supersedes**: 20260101-000000-aaaaaaa\n"
            )
            self.assertEqual(plots._superseding_sibling(old), new)


class TestCommittedPlots(unittest.TestCase):
    """The real tree: the same gate `npm run check:report` runs."""

    def test_every_spec_row_id_is_in_the_report_manifest(self):
        for spec in plots.PLOTS:
            with self.subTest(plot=spec.key):
                self.assertIn("—", plots.spec_row_label(spec.spec_row))

    def test_every_plot_has_a_renderer_and_a_loader(self):
        keys = {spec.key for spec in plots.PLOTS}
        self.assertEqual(keys, set(plots.LOADERS))
        self.assertEqual(keys, set(plots.RENDERERS))

    def test_committed_plots_are_fresh(self):
        problems = plots.check()
        self.assertEqual(
            problems,
            [],
            "docs/plots/ is stale against its evidence -- re-render per "
            "sim/report/plots-requirements.txt",
        )

    def test_at_least_the_enob_distribution_is_committed(self):
        # The issue's one mandatory figure.
        enob = REPO_ROOT / "docs/plots/enob-distribution.svg"
        self.assertTrue(enob.is_file(), f"{enob} must be committed")


class TestCdacMonteCarloDistributions(unittest.TestCase):
    """Both Monte Carlo series come out of the campaign's own committed draw
    logs, at the estimator its record prints."""

    @classmethod
    def setUpClass(cls):
        cls.data = plots.load_cdac_inl_distribution()
        record = REPO_ROOT / f"sim/cdac-array-transfer/records/{plots.CDAC_MC_RECORD_ID}.md"
        cls.stated = plots._cdac_mc_stated_rows(record)

    def test_every_draw_log_the_figure_hashes_is_committed(self):
        self.assertEqual(len(plots.CDAC_MC_DRAW_LOGS), plots.CDAC_MC_N)
        for rel in plots.CDAC_MC_DRAW_LOGS:
            with self.subTest(log=rel):
                self.assertTrue((REPO_ROOT / rel).is_file(), f"{rel} must be committed")

    def test_both_series_are_derived_per_draw_not_summarized(self):
        for key in ("inl", "dnl"):
            with self.subTest(series=key):
                self.assertEqual(len(self.data["series"][key]["values"]), plots.CDAC_MC_N)

    def test_drawn_statistics_reproduce_the_record_at_its_own_precision(self):
        for key, row_name in (("inl", "max|INL|"), ("dnl", "max|DNL|")):
            row = self.stated[row_name]
            entry = self.data["series"][key]
            for label, column in (("mean", 1), ("stdev", 2), ("min", 3), ("max", 4)):
                with self.subTest(series=key, statistic=label):
                    self.assertAlmostEqual(round(entry[label], 4), float(row[column]), places=9)

    def test_sigma_is_the_records_population_estimator_not_the_yield_reports(self):
        """The defect this guards: the figure used to print the yield report's
        sample (n-1) stddev while its record prints the population one."""
        import statistics

        report = json.loads((REPO_ROOT / plots.CDAC_MC_YIELD).read_text())
        by_name = {m["name"]: m for m in report["measurements"]}
        for key, measurement in (("inl", "inl_max_lsb"), ("dnl", "dnl_max_lsb")):
            with self.subTest(series=key):
                values = self.data["series"][key]["values"]
                sample_sigma = statistics.stdev(values)
                reported_sigma = float(by_name[measurement]["distribution"]["stddev"])
                # The yield report carries the (n-1) estimator ...
                self.assertAlmostEqual(reported_sigma, sample_sigma, places=9)
                # ... and the two estimators genuinely differ at the record's
                # printed precision, so drawing the wrong one is observable.
                self.assertNotEqual(
                    round(sample_sigma, 4), round(statistics.pstdev(values), 4)
                )
                # The figure draws the record's.
                self.assertAlmostEqual(
                    self.data["series"][key]["stdev"], statistics.pstdev(values), places=12
                )

    def test_a_wrong_sigma_is_caught_by_the_cross_check(self):
        """`--check` must fail on an estimator swap, not just on a moved file."""
        with self.assertRaises(plots.ProvenanceError):
            plots._agree(
                "max|INL| stdev",
                round(self.data["series"]["inl"]["stdev"], 4),
                round(self.data["series"]["inl"]["stdev"] + 0.0026, 4),
                tolerance=1e-9,
                where="estimator swap",
            )


if __name__ == "__main__":
    unittest.main()

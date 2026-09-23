"""Unit tests for signoff/check_evidence_hashes.py -- pure file reads, no
ngspice/PDK/klt required (mirrors sim/tests/test_proposal_citations.py's
PDK-free unit-test convention).

These live under sim/tests/ because that is this repo's only unittest root
(`npm run test:unit` discovers from there), not because the checker belongs to
the simulation harness -- it checks signoff/block-manifest.json.

The load-bearing tests are the NEGATIVE controls. The checker exists to close
exactly one hole: `klt signoff` compares a manifest's pinned `content_hash`
against the cited envelope's own self-reported hash, and nothing in that
comparison ever reads the artifact. So a checker that cannot fail when the
artifact is rewritten underneath a still-agreeing manifest/envelope pair is a
vacuous gate, and would be worse than no gate at all -- it would be a green
check standing where the staleness rule is supposed to stand. Each drift shape
is therefore asserted directly on a fixture:

  - the artifact changed while manifest and envelope still agree (the whole
    point);
  - the manifest pin and the envelope's recorded hash disagree (the half `klt
    signoff` also catches, asserted here because this checker must hold it
    without `klt` installed);
  - a pin against an envelope that records no hash at all, which can never be
    matched and must not pass silently;
  - the artifact an envelope names is not in the repo at all;
  - an unpinned `lvs` envelope (klt 0.5.0 writes `provenance.input: null`)
    whose `environment.*_sha256` no longer matches the committed netlists.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
SIGNOFF_DIR = REPO_ROOT / "signoff"
sys.path.insert(0, str(SIGNOFF_DIR))

import check_evidence_hashes as checker  # noqa: E402


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class FixtureTree:
    """A throwaway repo-shaped tree the checker can be pointed at."""

    def __init__(self, stack: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory()
        stack.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "signoff").mkdir(parents=True)
        (self.root / "evidence").mkdir(parents=True)
        original_root = checker.REPO_ROOT
        checker.REPO_ROOT = self.root
        stack.addCleanup(lambda: setattr(checker, "REPO_ROOT", original_root))

    def write(self, relative: str, payload: bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def write_json(self, relative: str, document: dict) -> Path:
        return self.write(relative, json.dumps(document).encode())

    def check(self, manifest: dict) -> list[str]:
        """Run every citation in `manifest` and return the failure list."""
        failures: list[str] = []
        notes: list[str] = []
        for item_key, entry in checker.iter_citations(manifest):
            checker.check_citation(item_key, entry, failures, notes)
        return failures


class DrcCitationTests(unittest.TestCase):
    def setUp(self):
        self.tree = FixtureTree(self)
        self.gds = b"GDS-fixture-bytes"
        self.tree.write("evidence/top.gds", self.gds)
        # `klt drc` records `file` as the ABSOLUTE path it was invoked with,
        # which for this repo's flows is a path inside a since-deleted agent
        # worktree. The fixture reproduces that shape deliberately: the
        # basename-beside-the-envelope fallback is the only reading that
        # resolves it, and it is the one the real citations depend on.
        self.envelope = {
            "status": "clean",
            "violations": [],
            "deck": {"name": "sky130"},
            "file": "/nonexistent/worktree/evidence/top.gds",
            "provenance": {"input": {"content_hash": sha256_bytes(self.gds)}},
        }
        self.tree.write_json("evidence/drc.json", self.envelope)
        self.manifest = {
            "block": "fixture",
            "kind": "analog",
            "evidence": {
                "3": {
                    "file": "evidence/drc.json",
                    "content_hash": sha256_bytes(self.gds),
                }
            },
        }

    def test_passes_when_artifact_matches(self):
        self.assertEqual(self.tree.check(self.manifest), [])

    def test_fails_when_the_artifact_changed_underneath_an_agreeing_pair(self):
        """The hole this checker exists to close.

        Manifest pin and envelope hash still agree with each other -- `klt
        signoff` would render this item `met` with `input_verified: null` --
        but the GDS on disk is a different revision.
        """
        self.tree.write("evidence/top.gds", b"GDS-fixture-bytes-REVISED")
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("hashes to", failures[0])
        self.assertIn("The artifact changed under the evidence", failures[0])

    def test_fails_when_the_pin_disagrees_with_the_envelope(self):
        self.manifest["evidence"]["3"]["content_hash"] = sha256_bytes(b"something else")
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("manifest pin", failures[0])

    def test_fails_when_pinning_an_envelope_that_records_no_hash(self):
        self.envelope["provenance"] = {"input": None}
        self.tree.write_json("evidence/drc.json", self.envelope)
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("records no provenance.input.content_hash", failures[0])

    def test_fails_when_the_named_artifact_is_not_in_the_repo(self):
        (self.tree.root / "evidence" / "top.gds").unlink()
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("does not resolve to a committed file", failures[0])

    def test_fails_when_the_cited_envelope_is_missing(self):
        (self.tree.root / "evidence" / "drc.json").unlink()
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("does not exist", failures[0])


class GenericCitationTests(unittest.TestCase):
    """Item 8's generic envelope -- the citation `klt signoff` can NEVER
    anchor to an artifact, because a generic envelope's author chooses their
    own field names."""

    def setUp(self):
        self.tree = FixtureTree(self)
        self.report = b"# characterization report\n"
        self.tree.write("docs/characterization-report.md", self.report)
        self.tree.write_json(
            "signoff/evidence/characterization.generic.json",
            {
                "schema_version": 1,
                "kind": "generic",
                "status": "pass",
                "source": "docs/characterization-report.md",
                "provenance": {"input": {"content_hash": sha256_bytes(self.report)}},
            },
        )
        self.manifest = {
            "block": "fixture",
            "kind": "mixed-signal",
            "evidence": {
                "8.analog": {
                    "file": "signoff/evidence/characterization.generic.json",
                    "content_hash": sha256_bytes(self.report),
                }
            },
        }

    def test_passes_when_the_wrapped_record_matches(self):
        self.assertEqual(self.tree.check(self.manifest), [])

    def test_fails_when_the_wrapped_record_was_regenerated(self):
        self.tree.write("docs/characterization-report.md", b"# characterization report v2\n")
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("hashes to", failures[0])

    def test_generic_marker_beats_a_colliding_native_field(self):
        """`"kind": "generic"` is checked ahead of every structural test, the
        same way the grader checks it, so a colliding field cannot reclassify
        the envelope into a native kind with a different artifact field."""
        envelope = json.loads(
            (self.tree.root / "signoff/evidence/characterization.generic.json").read_text()
        )
        envelope["violations"] = []
        envelope["deck"] = {"name": "sky130"}
        self.tree.write_json("signoff/evidence/characterization.generic.json", envelope)
        self.assertEqual(checker.classify(envelope), "generic")
        self.assertEqual(self.tree.check(self.manifest), [])


class UnpinnedLvsCitationTests(unittest.TestCase):
    """Item 4's citation. klt 0.5.0's `klt lvs` writes `provenance.input:
    null`, so there is no hash for a manifest pin to match -- but the envelope
    does record `environment.{layout,reference}_sha256`, and an unpinnable
    citation must not become an unverifiable one."""

    def setUp(self):
        self.tree = FixtureTree(self)
        self.layout = b"* extracted netlist\n"
        self.reference = b"* reference netlist\n"
        self.tree.write("evidence/top.extract.lvs.spice", self.layout)
        self.tree.write("evidence/top.lvs-reference.spice", self.reference)
        self.tree.write_json(
            "evidence/lvs.json",
            {
                "status": "mismatch",
                "mismatches": [],
                "layout": "top.extract.lvs.spice",
                "reference": "top.lvs-reference.spice",
                "provenance": {"input": None},
                "environment": {
                    "layout_sha256": hashlib.sha256(self.layout).hexdigest(),
                    "reference_sha256": hashlib.sha256(self.reference).hexdigest(),
                },
            },
        )
        self.manifest = {
            "block": "fixture",
            "kind": "analog",
            "evidence": {"4": {"file": "evidence/lvs.json"}},
        }

    def test_passes_when_both_netlists_match(self):
        self.assertEqual(self.tree.check(self.manifest), [])

    def test_fails_when_the_extracted_netlist_changed(self):
        self.tree.write("evidence/top.extract.lvs.spice", b"* extracted netlist v2\n")
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("environment.layout_sha256", failures[0])

    def test_fails_when_the_reference_netlist_changed(self):
        self.tree.write("evidence/top.lvs-reference.spice", b"* reference netlist v2\n")
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("environment.reference_sha256", failures[0])

    def test_fails_when_no_freshness_field_exists_at_all(self):
        envelope = json.loads((self.tree.root / "evidence/lvs.json").read_text())
        envelope["environment"] = {}
        self.tree.write_json("evidence/lvs.json", envelope)
        failures = self.tree.check(self.manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("cannot be verified at all", failures[0])


class CompoundAndCommandEntryTests(unittest.TestCase):
    def setUp(self):
        self.tree = FixtureTree(self)

    def test_item_11_compound_array_is_flattened(self):
        """Item 11 is the one item whose evidence entry may be a JSON array.
        Every part must be checked, not just the first -- a silently dropped
        part is exactly how an unproven power-delivery claim would sneak in."""
        manifest = {
            "block": "fixture",
            "kind": "analog",
            "evidence": {"11": ["evidence/erc.json", {"file": "evidence/lvs.json"}]},
        }
        self.assertEqual(
            [key for key, _ in checker.iter_citations(manifest)], ["11[0]", "11[1]"]
        )
        failures = self.tree.check(manifest)
        self.assertEqual(len(failures), 2, failures)

    def test_command_backed_entry_is_refused_not_ignored(self):
        manifest = {
            "block": "fixture",
            "kind": "analog",
            "evidence": {"5": {"command": ["klt", "sim", "corners.json"]}},
        }
        failures = self.tree.check(manifest)
        self.assertEqual(len(failures), 1, failures)
        self.assertIn("command-backed evidence is not supported", failures[0])


class CommittedManifestTests(unittest.TestCase):
    """The real manifest, against the real tree. This is the check `npm run
    check:ci` runs; asserting it here too means a `test:unit` run catches the
    same drift even if the check:ci wiring is ever removed."""

    def test_committed_manifest_passes(self):
        failures: list[str] = []
        notes: list[str] = []
        manifest = json.loads((SIGNOFF_DIR / "block-manifest.json").read_text())
        for item_key, entry in checker.iter_citations(manifest):
            checker.check_citation(item_key, entry, failures, notes)
        self.assertEqual(failures, [])
        self.assertTrue(notes, "no artifact was re-hashed -- the gate would be vacuous")

    def test_committed_manifest_declares_block_and_kind(self):
        manifest = json.loads((SIGNOFF_DIR / "block-manifest.json").read_text())
        self.assertEqual(manifest.get("block"), "sky130-sar-adc")
        self.assertIn(manifest.get("kind"), ("analog", "digital", "mixed-signal"))

    def test_mixed_signal_manifest_declares_its_partition_boundary(self):
        """`design-evidence-tiers.md`'s "Block kind" section requires a
        mixed-signal claim to state which nets/cells belong to which side.
        `klt signoff` reports that declaration but cannot grade it, so the
        obligation to actually make it is enforced here."""
        manifest = json.loads((SIGNOFF_DIR / "block-manifest.json").read_text())
        if manifest.get("kind") != "mixed-signal":
            self.skipTest("not a mixed-signal manifest")
        boundary = manifest.get("partition_boundary")
        self.assertIsInstance(boundary, dict)
        self.assertEqual(set(boundary), {"analog", "digital"})
        for partition, statement in boundary.items():
            self.assertIsInstance(statement, str)
            self.assertGreater(len(statement.strip()), 40, partition)


if __name__ == "__main__":
    unittest.main()

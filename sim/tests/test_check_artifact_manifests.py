"""Tests for sim/check_artifact_manifests.py (issue #717). Builds throwaway
git repositories; no broker is contacted."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

import check_artifact_manifests as chk  # noqa: E402

SHA = "ab" * 32
NAME = "sim/exp/corners/r1/a.log"
ENTRY = {
    "sha256": SHA, "size": 5, "kind": "evidence",
    "producer": {"tool": "klt", "version": "1", "loom.repo": "o/n", "commit": None},
    "uri": f"artifact:evidence/o__n/ab/{SHA}", "name": NAME,
}
MANIFEST = {"schema_version": 1, "entries": [ENTRY]}


def _entry(**kw):
    e = copy.deepcopy(ENTRY)
    e.update(kw)
    return e


class TestSchema(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(chk.manifest_problems(MANIFEST), [])

    def _bad(self, entry, needle):
        probs = chk.manifest_problems({"schema_version": 1, "entries": [entry]})
        self.assertTrue(any(needle in p for p in probs), probs)

    def test_non_artifact_uris_rejected(self):
        self._bad(_entry(uri=f"s3://bucket/evidence/o__n/ab/{SHA}"), "artifact:<key>")
        self._bad(_entry(uri=f"https://x/evidence/o__n/ab/{SHA}"), "artifact:<key>")

    def test_uri_key_must_end_in_sha(self):
        self._bad(_entry(uri="artifact:evidence/o__n/ab/" + "cd" * 32), "sha256")

    def test_uri_repo_must_match_producer(self):
        self._bad(_entry(uri=f"artifact:evidence/x__y/ab/{SHA}"), "different repo")

    def test_unknown_and_missing_fields(self):
        self._bad(_entry(extra=1), "unknown")
        e = _entry()
        del e["producer"]
        self._bad(e, "missing")

    def test_name_must_be_canonical_sim_path(self):
        for n in ("/abs/x", "sim/../x", "other/x", "sim/a//b"):
            self._bad(_entry(name=n), "canonical")

    def test_zero_entries_and_duplicates(self):
        self.assertTrue(chk.manifest_problems({"schema_version": 1, "entries": []}))
        dup = {"schema_version": 1, "entries": [ENTRY, ENTRY]}
        self.assertTrue(any("duplicate" in p for p in chk.manifest_problems(dup)))

    def test_bucket_string_not_accepted(self):
        self._bad(_entry(uri="s3://b/k"), "artifact:<key>")


class TestCheckTree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._git("init", "-q")

    def _git(self, *a):
        subprocess.run(["git", "-C", str(self.root), "-c", "user.email=a@b", "-c",
                        "user.name=t", *a], check=True, capture_output=True)

    def _put(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def _run(self):
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "x")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = chk.main(["check", "--repo", str(self.root), "--tree", "HEAD"])
        return rc, out.getvalue(), err.getvalue()

    def test_valid_manifest_passes_and_says_not_verified(self):
        self._put("manifests/artifacts/exp-r1.manifest.json", json.dumps(MANIFEST))
        rc, out, _ = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("NOT hash-verified", out)

    def test_committed_bytes_beside_manifest_fail(self):
        self._put("manifests/artifacts/exp-r1.manifest.json", json.dumps(MANIFEST))
        self._put(NAME, "alpha\n")
        rc, _, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("must not also be committed", err)

    def test_malformed_json_and_stray_files_fail(self):
        self._put("manifests/artifacts/exp-r1.manifest.json", "{")
        self._put("manifests/artifacts/notes.txt", "x")
        rc, _, err = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("not valid JSON", err)
        self.assertIn("notes.txt", err)

    def test_no_manifests_is_ok(self):
        self.assertEqual(self._run()[0], 0)

    def test_verify_without_broker_is_nonzero(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(chk.ENV_BROKER, None)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(chk.main(["verify", "m.json"]), chk.EXIT_ERROR)


class TestRepoHygiene(unittest.TestCase):
    def test_no_bucket_or_account_in_committed_manifests(self):
        root = SIM_DIR.parent
        out = subprocess.run(["git", "-C", str(root), "grep", "-nE", r"s3://|arn:aws:",
                              "--", "manifests/"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 1, out.stdout)


if __name__ == "__main__":
    unittest.main()

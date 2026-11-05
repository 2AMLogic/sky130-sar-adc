"""evidence.sha256_bytes_file is binary-safe (unlike text-based sha256_file)
and is the single file-hash helper the digital sim run drivers import."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence  # noqa: E402


class TestSha256BytesFile(unittest.TestCase):
    def test_matches_read_bytes_digest_for_non_utf8_multichunk(self):
        data = bytes(range(256)) * 10000  # > 1 MiB, invalid UTF-8
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.gds"
            p.write_bytes(data)
            want = hashlib.sha256(data).hexdigest()
            self.assertEqual(evidence.sha256_bytes_file(p), want)
            self.assertEqual(evidence.sha256_bytes_file(str(p)), want)

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e"
            p.write_bytes(b"")
            self.assertEqual(evidence.sha256_bytes_file(p), hashlib.sha256(b"").hexdigest())


if __name__ == "__main__":
    unittest.main()

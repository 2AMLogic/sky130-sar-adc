"""The klt-yield pin hint must track sim/yield-requirements.txt (issue #803)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence  # noqa: E402


class YieldPinHintTest(unittest.TestCase):
    def test_hint_matches_committed_pin(self):
        pins = [
            ln.strip()
            for ln in evidence.YIELD_REQUIREMENTS.read_text().splitlines()
            if ln.strip().startswith("klayout-tools[yield]==")
        ]
        self.assertEqual(len(pins), 1)
        self.assertIn(pins[0], evidence.YIELD_PIN_HINT)

    def test_hint_follows_requirements_file(self):
        with tempfile.TemporaryDirectory() as d:
            req = Path(d) / "r.txt"
            req.write_text("# c\nklayout-tools[yield]==9.9.9\n")
            self.assertIn("klayout-tools[yield]==9.9.9", evidence.yield_pin_hint(req))

    def test_hint_falls_back_when_unreadable(self):
        hint = evidence.yield_pin_hint(Path("/nonexistent/req.txt"))
        self.assertIn("sim/yield-requirements.txt", hint)
        self.assertNotIn("==", hint)


if __name__ == "__main__":
    unittest.main()

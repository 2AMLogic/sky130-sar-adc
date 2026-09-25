"""Import-smoke coverage for the `layout/*/bin/` entry-point scripts (issue
#399) -- pure stdlib, no PDK/ngspice/KLayout required, so it belongs to the
headless tier (`npm run test` -> `test:unit`, run by CI's "Repo checks
(headless, no PDK)" job; mirrors sim/tests/test_harness.py's PDK-free unit-test
convention, see sim/selftest.sh stage 1/4).

Why this exists
---------------
`DOMAIN_TAP_NET` has been deleted from
`layout/sampling-frontend{,-wells}/bin/gen_blocks.py` as an "unused import"
three times (#251, #383/PR #388, #394/PR #398). PR #388 landed that deletion on
`main`, breaking four scripts at *import* time, and every gate stayed green:

* `npm run test:compile` runs `py_compile`, which parses and byte-compiles a
  module but never executes it -- a missing re-export is invisible to it;
* `npm run test:unit` discovered only `sim/tests`, and nothing there imported
  anything under `layout/`;
* `.github/workflows/ci.yml` runs no layout entry point headlessly.

PR #398 restored the name with an explanatory comment and an `F401` noqa. That
helps a *reader*, but it cannot make CI fail if the line is deleted anyway.
This module is the mechanical guard: it actually executes the import of every
`layout/*/bin/{build_layout,gen_blocks,render-record}.py` and fails on any
exception. Reverting PR #398's two re-export lines makes it red.

Why a subprocess per script (and not one shared interpreter)
------------------------------------------------------------
Three sibling `gen_blocks.py` modules exist (`sampling-frontend`,
`sampling-frontend-wells`, `comparator`) and each block's scripts put their own
`bin/` directory first on `sys.path`, so they all claim the *same* top-level
module name `gen_blocks`. Importing two of them into one interpreter makes the
first one's `sys.modules['gen_blocks']` entry satisfy the second one's
`from gen_blocks import ...`, which yields a bogus verdict either way -- in
this repo it currently produces a false FAILURE:

    ImportError: cannot import name 'DEVICES' from 'gen_blocks'
    (layout/sampling-frontend/bin/gen_blocks.py)

raised while importing `layout/sampling-frontend-wells/bin/build_layout.py`,
whose own `gen_blocks` does define `DEVICES`. A fresh interpreter per script is
also the faithful reproduction of how `run-flow.sh` actually invokes them.

The probe replicates each script's own two-line `sys.path` prelude (its own
`bin/` first, then the shared `layout/bin/`) and loads the file through
`importlib.util.spec_from_file_location`, which is required anyway because
`render-record.py`'s hyphen makes it unimportable by module name. The loaded
module is given a name other than `__main__`, so each script's
`if __name__ == "__main__":` block does not run -- this checks imports, it does
not execute flows.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAYOUT_DIR = REPO_ROOT / "layout"

# The entry-point filenames each block directory may carry. `layout/bin/` holds
# shared helpers (`_gen_common.py`, `_record_common*.py`, ...) plus its own
# top-level `render-record.py`; none of those are block entry points and the
# `*/bin/` glob below does not reach them (`layout/bin/...` has one path
# component too few to match).
ENTRY_POINT_NAMES = ("build_layout.py", "gen_blocks.py", "render-record.py")

# Scripts that genuinely cannot be imported without a PDK/KLayout/ngspice
# belong here, keyed by path relative to the repo root, with the reason. Empty
# today: all discovered scripts import cleanly on a bare interpreter. Prefer
# adding an entry here over deleting or weakening the test.
IMPORT_SKIPS: dict[str, str] = {}

# Scripts whose import break is the specific regression this module exists to
# catch (#251, #383/PR #388, #394/PR #398). Asserted present so that a future
# refactor which moves or renames them cannot silently empty the inventory and
# leave this suite vacuously green.
REGRESSION_WITNESSES = (
    "layout/sampling-frontend/bin/gen_blocks.py",
    "layout/sampling-frontend-wells/bin/gen_blocks.py",
    "layout/sampling-frontend/bin/build_layout.py",
    "layout/sampling-frontend/bin/render-record.py",
    "layout/sampling-frontend-wells/bin/build_layout.py",
    "layout/sampling-frontend-wells/bin/render-record.py",
)

# Executed by a fresh interpreter, one per script; the script path is argv[1].
IMPORT_PROBE = """\
import importlib.util
import sys
from pathlib import Path

script = Path(sys.argv[1]).resolve()
# The same two-line prelude every one of these scripts sets up for itself:
# the shared layout/bin/ helpers, then the script's own bin/ ahead of it.
sys.path.insert(0, str(script.parent.parent.parent / "bin"))
sys.path.insert(0, str(script.parent))

spec = importlib.util.spec_from_file_location("_entrypoint_under_test", script)
module = importlib.util.module_from_spec(spec)
sys.modules["_entrypoint_under_test"] = module
spec.loader.exec_module(module)
"""


def discover_entry_points() -> list[Path]:
    """Every `layout/<block>/bin/<entry point>.py`, sorted, repo-relative
    order. Hidden directories (`layout/.venv/`, `layout/.venv-erc/`) are
    excluded to match `package.json`'s own lint/compile exclusions."""
    found: set[Path] = set()
    for name in ENTRY_POINT_NAMES:
        for path in LAYOUT_DIR.glob(f"*/bin/{name}"):
            if path.relative_to(LAYOUT_DIR).parts[0].startswith("."):
                continue
            found.add(path)
    return sorted(found)


class TestEntryPointInventory(unittest.TestCase):
    """Guard the discovery itself: a glob that matches nothing would make
    TestEntryPointImports pass vacuously, reproducing the very blind spot this
    module was added to close."""

    def test_inventory_is_not_empty(self):
        self.assertTrue(
            discover_entry_points(),
            f"no layout entry-point scripts matched {ENTRY_POINT_NAMES} under "
            f"{LAYOUT_DIR}/*/bin/ -- the discovery glob is broken, or the "
            "scripts moved; fix the glob rather than deleting this test",
        )

    def test_inventory_contains_the_regression_witnesses(self):
        discovered = {
            str(path.relative_to(REPO_ROOT)) for path in discover_entry_points()
        }
        for witness in REGRESSION_WITNESSES:
            with self.subTest(script=witness):
                self.assertIn(
                    witness, discovered,
                    f"{witness} is one of the scripts the recurring "
                    "DOMAIN_TAP_NET import break (#251/#383/#394) actually "
                    "broke; if it legitimately moved, update "
                    "REGRESSION_WITNESSES to its new path -- do not just drop "
                    "it, or this suite stops covering the regression",
                )


class TestEntryPointImports(unittest.TestCase):
    def test_every_entry_point_imports_cleanly(self):
        for script in discover_entry_points():
            relative = str(script.relative_to(REPO_ROOT))
            with self.subTest(script=relative):
                if relative in IMPORT_SKIPS:
                    self.skipTest(IMPORT_SKIPS[relative])
                proc = subprocess.run(
                    [sys.executable, "-c", IMPORT_PROBE, str(script)],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(
                    proc.returncode, 0,
                    f"{relative} failed to import (exit {proc.returncode}). "
                    "These scripts must import cleanly on a bare interpreter "
                    "-- if this is a missing name, restore it (see the "
                    "DOMAIN_TAP_NET history in this module's docstring); if "
                    "the script now genuinely needs a PDK/KLayout/ngspice at "
                    "import time, add it to IMPORT_SKIPS with a reason.\n"
                    f"--- stderr ---\n{proc.stderr}",
                )


if __name__ == "__main__":
    unittest.main()

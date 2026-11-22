"""Per-campaign modules behind `sim/supply-impedance-sensitivity/run_supply_impedance.py` (issue #848).

A behavior-preserving split of the former single-module runner, mirroring the
`comparator_campaigns/` layout issue #613 landed for the comparator driver.
`run_supply_impedance.py` stays the CLI entry point and keeps its module
docstring, its argument parser and `main()`.

`common` holds everything two or more campaigns use; each other module holds
one campaign's constants, arm builders, findings prose and record writer, and
imports `common` only -- never another campaign module. Importing the package
puts `sim/` and `sim/full-conversion-transient/` on `sys.path` (for `harness`
and `run_conversion`), which `common` does at import time.
"""
from . import common  # noqa: F401

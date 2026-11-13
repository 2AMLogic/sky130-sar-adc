"""Per-campaign modules behind `sim/full-conversion-transient/run_conversion.py` (issue #861).

A behavior-preserving split of the former single-module driver, mirroring the
`comparator_campaigns/` (#613) and `supply_impedance_campaigns/` (#848)
layouts. `run_conversion.py` stays the CLI entry point and keeps its module
docstring, its argument parser and `main()`; every path, flag and record
format is unchanged, and this split minted no new evidence.

`common` holds everything two or more campaigns use; each other module holds
one campaign's constants, measure-card builders, decode helpers and record
writer, and imports `common` only -- never another campaign module. Importing
the package puts `sim/` and `sim/full-conversion-transient/` on `sys.path`
(for `harness`, `dynamic_enob` and `gen_full_conversion_tb`), which `common`
does at import time.

  common           shared core (see its own docstring for what is shared and
                   why `EXPERIMENT_DIR` / `assemble_deck` / `_run_ngspice`
                   are read as attributes of it)
  dc_codes         the base DC-code campaign's record
  node_trace       --node-trace
  cm_trace         --cm-trace
  decision_margin  --decision-margin-trace
  coherent_sine    --coherent-sine, with its switching-event trace prose
  solver_audit     --solver-audit
"""
from . import common  # noqa: F401

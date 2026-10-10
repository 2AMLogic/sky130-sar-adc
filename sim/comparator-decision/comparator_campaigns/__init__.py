"""Per-campaign modules behind sim/comparator-decision/run.py (issue #613).

Behavior-preserving split of the former single-module driver; `run.py` is the
CLI dispatcher. Importing the package puts sim/ on sys.path (for `harness`).
"""
from . import common  # noqa: F401

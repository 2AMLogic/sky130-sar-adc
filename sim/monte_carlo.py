#!/usr/bin/env python3
"""Monte Carlo runner for sky130-sar-adc.

    python3 sim/monte_carlo.py --list
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8
    python3 sim/monte_carlo.py mc-smoke --seed 1 --n 8 --record

Stdlib only, no virtualenv required. See sim/harness/mc_cli.py for the full
CLI and sim/README.md for the evidence-record format (recorded seed, N, and
the deterministic negative control) this writes.

This is the piece a SAR ADC needs beyond a bandgap/PLL harness: ENOB, INL,
DNL, and offset are statistical rows, not corner points -- see
spec/target-spec.md "What T1 (bronze) will require of this block". Issue #2
proves the mechanism against a harness-proof circuit (sim/mc-smoke/); a
future ADC testbench manifest reuses this exact runner.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.mc_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

"""sim/harness -- PVT corner + Monte Carlo simulation harness for sky130-sar-adc.

Stdlib only (see docs/environment-setup.md and sim/README.md). Bootstrapped
in issue #2, adapting the *pattern* of 2AMLogic/gf180-sar-adc's
sim/harness/ (commit f613571aee5b80eff1eea37bdce9dfc88c5cf396) and
2AMLogic/sky130-bandgap's sim/ scaffolding (commit
1f04e8524cc2d8c2c7154773749b1b2d3be2ce64) to sky130 -- not a byte-for-byte
port; this repo has no ADC schematic yet, so the module boundaries here are
sized for what issue #2 needs to prove (the PVT/MC plumbing works) rather
than gf180-sar-adc's full, decade-of-testbenches harness surface.
"""

__version__ = "0.1.0"

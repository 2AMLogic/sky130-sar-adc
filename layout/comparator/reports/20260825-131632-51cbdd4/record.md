# Comparator layout record: 20260825-131632-51cbdd4

Physical layout for the dynamic comparator sub-block (issue #101), drawn from design/comparator.sch via `klt gen` (per-device/pair matched blocks) + `klt gen-compose` (place + route). **Overall verdict: PARTIAL** -- see README.md "Composition status" for the full, honest writeup; this record is the specific numbers behind that writeup, not a DRC/LVS-clean claim.

## Provenance
- `klt` version: klt 0.3.0
- PDK variant: sky130A
- repo commit: `51cbdd44f00b8232744c8a8acc50fb269c0969af` (dirty)

## Composition (`klt gen-compose`)
- overall: every block placed; net-by-net routing status below
  - `VINN`: **routed** (1/1 legs routed)
  - `VINP`: **unrouted** (0/1 legs routed)
  - `GND`: **partial** (1/3 legs routed)
  - `CLK`: **routed** (2/2 legs routed)
  - `TAIL`: **partial** (3/7 legs routed)
  - `VDD`: **partial** (2/6 legs routed)
  - `OUTP`: **partial** (3/20 legs routed)
  - `OUTN`: **unrouted** (0/21 legs routed)

## DRC (sky130 deck, on the composed layout)
- **VIOLATIONS** -- 10 violations: {'li1.space.1': 2, 'met1.space.1': 8}
- every violation traces to metal `klt gen-compose` itself drew while resolving a `routed: true` connectivity leg (every input `klt gen` block is independently DRC-clean in isolation -- see README.md "Composition status"); filed generically at 2AMLogic/klayout-tools per CLAUDE.md's friction protocol (see README.md for the issue link).

## Extract
- device_count=11 net_count=24 pin_count=7

## LVS (vs. reference.spice)
- verdict: **mismatch**
- mismatch_count=54
- devices: layout=11 reference=9 matched=0
- nets: layout=24 reference=8 matched=0
- **expected, not a surprise**: the composition step above left several connectivity[] legs unrouted/partial (same-facing multi-block bus routing gap, see README.md); an unrouted net is a real open circuit in the drawn geometry, so LVS correctly reports it as a mismatch rather than a false pass. This is the concrete, falsifiable signal that composition is not yet complete -- not a reference-netlist authoring error (reference.spice is the schematic-correct target this layout is converging toward, not hand-tuned to match today's partial routing).


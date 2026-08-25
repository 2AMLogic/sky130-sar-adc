# SAR sequencer layout record: 20260825-124031-1a2f7c1

## Provenance
- `klt` version: klt 0.2.0
- OpenROAD version: 26Q3-1510-g6cb3f2b704
- PDK variant: sky130A
- repo commit: `1a2f7c11cca9990c2f731bab2efd9b52e78c1939` (dirty)

## Place-and-route
- stage reached: **route**
- die area: 1812.2 um^2
- utilization: 51.5292%
- wirelength: 1288 um
- worst setup slack: 81.8934 ns (setup violations: 0, hold violations: 0)
- fmax: 696.086 MHz
- estimated power: 0.0155 mW

## DRC (sky130 deck)
- **CLEAN** -- 0 violations

## LVS (layout vs. post-route netlist)
- verdict: **mismatch**
- devices: layout=760 reference=760 matched=0
- nets: layout=539 reference=395 matched=0
- **known blocker**: `klt extract`'s pin/net-name promotion for a `klt place-and-route`-produced (DEF->GDS-merged) layout does not reliably distinguish a genuine top-level design port from the many per-instance local-pin-name labels DEF's own NETS section records at every routed connection point -- this prevents `klt lvs`'s `NetlistComparer` from establishing net/device correspondence, even though device counts match exactly against a reference mechanically flattened from the *actual post-route* netlist (see layout/sar-sequencer/README.md, "LVS reference provenance", and the filed klayout-tools issue).


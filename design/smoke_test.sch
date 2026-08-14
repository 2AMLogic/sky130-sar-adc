v {xschem version=3.4.7 file_version=1.2
* smoke_test.sch — environment-bootstrap smoke test (issue #2)
*
* Throwaway circuit only: a resistor divider built from two sky130
* generic poly resistor primitives (sky130_fd_pr__res_generic_po),
* driven by a fixed DC source. This exercises xschem netlisting and
* ngspice model resolution against the sky130 PDK without containing
* any SAR ADC design content, spec values, or proprietary IP — see
* docs/environment-setup.md for how this is run.
*
* Provenance: ported verbatim (topology + xschem idiom) from
* 2AMLogic/sky130-bandgap's design/smoke_test.sch (issue #17 there,
* commit 1f04e8524cc2d8c2c7154773749b1b2d3be2ce64), per CLAUDE.md's
* "Harness bootstrap" instruction to copy the sim-harness/PDK-flow
* pattern rather than reinvent it. Only the provenance comments and
* the title-block author differ.
}
G {}
V {}
S {}
E {}
N 0 30 300 30 {lab=VDD}
N 300 -30 300 -130 {lab=OUT}
C {devices/vsource.sym} 0 0 0 0 {name=V1 value=1.8 savecurrent=false}
C {devices/gnd.sym} 0 -30 0 0 {name=l1 lab=GND}
C {sky130_fd_pr/res_generic_po.sym} 300 0 0 0 {name=R1 W=1 L=1 model=res_generic_po spiceprefix=X mult=1}
C {sky130_fd_pr/res_generic_po.sym} 300 -160 0 0 {name=R2 W=1 L=1 model=res_generic_po spiceprefix=X mult=1}
C {devices/gnd.sym} 300 -190 0 0 {name=l2 lab=GND}
C {devices/code.sym} 500 100 0 0 {name=MODELS
only_toplevel=true
format="tcleval( @value )"
value="
** sky130 PDK model include (tt corner) — see docs/environment-setup.md
.lib $::SKYWATER_MODELS/sky130.lib.spice tt
.op
"
spice_ignore=false}
C {devices/title.sym} 0 -260 0 0 {name=l3 author="2AM Logic (issue #2 smoke test, ported from sky130-bandgap issue #17)"}

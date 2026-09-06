"""Shared PFET device table for the sampling front end's two composition
studies.

Used by `layout/sampling-frontend-wells/bin/gen_blocks.py` (issue #122, the
n-well/body-tie composition) and `layout/sampling-frontend/bin/gen_blocks.py`
(issue #99, the full sub-block layout), which import this module via a
`sys.path` insert (see either script's own header) rather than a package
install, matching this directory's existing `_geometry_common.py` /
`_record_common.py` shared-module convention.

Both flows draw the exact same nine `sky130_fd_pr__pfet_01v8` instances of
`design/sampling_frontend.sch` -- same `(block id, schematic name, domain, W,
L)` values, same net wiring -- because the n-well/body-tie composition #122
proved is reused unmodified by #99's full layout, not re-derived. Before this
module existed, each script carried its own hand-transcribed copy of this
table with the trailing three net columns in a different order (S/G/D in the
wells flow, D/G/S in the full-layout flow) -- a duplication nothing enforced,
found and removed as issue #208.
"""
from __future__ import annotations

#: The three n-well domains the PFETs partition into, in left-to-right
#: floorplan order, mapped to the net each domain's well tap is routed to.
DOMAIN_TAP_NET = {
    "boost_p": "BOOST_P",
    "vdd": "VDD",
    "boost_n": "BOOST_N",
}

#: One row per `sky130_fd_pr__pfet_01v8` instance of
#: `design/sampling_frontend.sch`, transcribed from
#: `sim/sampling-frontend/testbench/sampling_frontend_dut.spice`'s
#: `X<name> D G S B sky130_fd_pr__pfet_01v8 L=.. W=..` cards:
#:
#:   XSa_p    BOOST_P SAMPLE  VDD     BOOST_P  L=0.5  W=1
#:   XScp_p   BSBOT_P SAMPLEB VINP    VDD      L=0.15 W=1
#:   XSe_p    G_P     SAMPLEB BOOST_P BOOST_P  L=0.15 W=1
#:   XCmswp_p BPREF_P SAMPLEB VCM     VDD      L=0.15 W=1
#:   XSa_n    BOOST_N SAMPLE  VDD     BOOST_N  L=0.5  W=1
#:   XScp_n   BSBOT_N SAMPLEB VINN    VDD      L=0.15 W=1
#:   XSe_n    G_N     SAMPLEB BOOST_N BOOST_N  L=0.15 W=1
#:   XCmswp_n BPREF_N SAMPLEB VCM     VDD      L=0.15 W=1
#:   XInvp    SAMPLEB SAMPLE  VDD     VDD      L=0.15 W=2
#:
#: ``body`` is not stored separately: it is ``DOMAIN_TAP_NET[domain]`` by
#: construction, which is exactly the invariant #122's flow exists to prove.
#: Order below is the floorplan order (all of one domain's devices adjacent),
#: which is what makes a single n-well rectangle per domain possible.
#:
#: Column order is (block id, schematic name, domain, W um, L um, D net,
#: G net, S net) -- normalized on D/G/S (the order `sim/`'s own SPICE cards
#: use) rather than the wells flow's original S/G/D, since every consumer
#: treats drain/source as an unordered pair already (a MOSFET's D/S is
#: interchangeable in the drawn geometry -- see either `render-record.py`'s
#: `_extracted_bodies` docstring).
PFET_DEVICES = [
    ("sa_p", "Sa_p", "boost_p", 1.0, 0.5, "BOOST_P", "SAMPLE", "VDD"),
    ("se_p", "Se_p", "boost_p", 1.0, 0.15, "G_P", "SAMPLEB", "BOOST_P"),
    ("scp_p", "Scp_p", "vdd", 1.0, 0.15, "BSBOT_P", "SAMPLEB", "VINP"),
    ("cmswp_p", "Cmswp_p", "vdd", 1.0, 0.15, "BPREF_P", "SAMPLEB", "VCM"),
    ("invp", "Invp", "vdd", 2.0, 0.15, "SAMPLEB", "SAMPLE", "VDD"),
    ("cmswp_n", "Cmswp_n", "vdd", 1.0, 0.15, "BPREF_N", "SAMPLEB", "VCM"),
    ("scp_n", "Scp_n", "vdd", 1.0, 0.15, "BSBOT_N", "SAMPLEB", "VINN"),
    ("se_n", "Se_n", "boost_n", 1.0, 0.15, "G_N", "SAMPLEB", "BOOST_N"),
    ("sa_n", "Sa_n", "boost_n", 1.0, 0.5, "BOOST_N", "SAMPLE", "VDD"),
]

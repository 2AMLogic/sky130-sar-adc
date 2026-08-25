#!/usr/bin/env python3
"""Emit the `klt gen-compose` request document that places and (attempts to)
route the comparator's five `klt gen` blocks (see gen_blocks.py) into one
composed cell, per design/comparator.sch's connectivity
(sim/comparator-decision/testbench/comparator_core.spice is the xschem-
derived device list this net-by-net wiring was checked against -- see that
file's header for the full D/G/S/B list this module's `net()` calls encode).

Placement: a single left-to-right row, `order=[tail, inpair, latn, latp,
rst]` -- `tail` immediately left of `inpair` so `tail`'s drain (TAIL net,
faces +x) meets `inpair`'s source ports (TAIL net, face -x) directly across
the gap; `inpair` immediately left of the three regeneration blocks so its
drain ports (OUTP/OUTN, face +x) face the row's remaining blocks.

Routing: `layer_role: "metal"` (met1) with `cross_block_layer_role:
"metal2"` -- every matched pair's own two interleaved/stacked legs (e.g.
`inpair`'s Q1_1_*/Q1_2_*) sit on a shared net that has to cross that same
block's own other pads to tie together (a same-block "self-net"), which
`layer_role` alone cannot draw without a same-layer short; `metal2` gives
that self-net tie a second level to hop to instead (see
`klayout_tools.gen_compose`'s own "Cross-block bus routing" docstring
section).

Known-incomplete (see layout/comparator/README.md "Composition status" for
the full, honest writeup this script's output is checked against): as of the
pinned `klt` 0.3.0 build, several `connectivity[]` bundle legs this document
declares come back `unrouted`/`partial` from `klt gen-compose` -- routing a
net shared by more than two same-facing (all-drain or all-source) block
ports in a single row is a real capability gap in the pinned build's
nearest-pair-first bundle router, not a mistake in this document's own net
list (cross-checked pin-for-pin against comparator_core.spice's device list
by this module's own `net()` calls). Filed generically at
2AMLogic/klayout-tools per CLAUDE.md's friction protocol (see README.md for
the issue link) -- this script still emits the *intended*, schematic-correct
connectivity regardless of what the pinned build manages to route, so a
future `klt` release that closes the gap will route more of it without any
change here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _pins(*specs: tuple[str, str]) -> list[dict[str, str]]:
    out = []
    for block, ports in specs:
        for port in ports.split():
            out.append({"block": block, "port": port})
    return out


def build_connectivity() -> list[dict[str, object]]:
    connectivity: list[dict[str, object]] = []

    def net(name: str, *specs: tuple[str, str]) -> None:
        connectivity.append({"net": name, "pins": _pins(*specs)})

    # `inpair`'s own two same-block self-nets (VINN, VINP) are declared
    # *before* any other net that also needs a metal2 same-block crossing
    # over `inpair` (TAIL) -- `klt gen-compose` routes connectivity[] entries
    # in document order and a later self-net can find its own block's metal2
    # lane already claimed by an earlier one (empirically observed: reversing
    # this order measurably changed which of {VINN, VINP, TAIL} routed).
    # M_INN=inpair.Q1 (D=OUTP G=VINN S=TAIL), M_INP=inpair.Q2 (D=OUTN G=VINP S=TAIL)
    net("VINN", ("inpair", "Q1_1_G Q1_2_G"))
    net("VINP", ("inpair", "Q2_1_G Q2_2_G"))

    # M_TAIL: D=TAIL G=CLK S=GND B=(vsubs, no ring drawn)
    net("GND", ("tail", "U0_S"), ("latn", "Q1_1_S Q2_1_S"))
    net("CLK", ("tail", "U0_G"), ("rst", "Q1_1_G Q2_1_G"))
    net("TAIL", ("tail", "U0_D"), ("inpair", "Q1_1_S Q1_2_S Q2_1_S Q2_2_S"))

    # M_LATP_P/N=latp.Q1/Q2 (S=VDD, cross-coupled D/G to OUTP/OUTN)
    # M_RST_P/N=rst.Q1/Q2 (S=VDD, G=CLK, D=OUTP/OUTN)
    net("VDD", ("latp", "Q1_1_S Q2_1_S"), ("rst", "Q1_1_S Q2_1_S"))

    # M_LATN_P=latn.Q1 (D=OUTP,G=OUTN,S=GND); M_LATN_N=latn.Q2 (D=OUTN,G=OUTP,S=GND)
    # M_LATP_P=latp.Q1 (D=OUTP,G=OUTN,S=VDD); M_LATP_N=latp.Q2 (D=OUTN,G=OUTP,S=VDD)
    # M_RST_P=rst.Q1 (D=OUTP,G=CLK,S=VDD);   M_RST_N=rst.Q2 (D=OUTN,G=CLK,S=VDD)
    net(
        "OUTP",
        ("inpair", "Q1_1_D Q1_2_D"),
        ("latn", "Q1_1_D Q2_1_G"),
        ("latp", "Q1_1_D Q2_1_G"),
        ("rst", "Q1_1_D"),
    )
    net(
        "OUTN",
        ("inpair", "Q2_1_D Q2_2_D"),
        ("latn", "Q2_1_D Q1_1_G"),
        ("latp", "Q2_1_D Q1_1_G"),
        ("rst", "Q2_1_D"),
    )
    return connectivity


def build_request() -> dict[str, object]:
    # `generator_report` paths are bare filenames -- resolved by `klt
    # gen-compose` relative to the request document's own directory
    # (`_resolve_relative`), so run-flow.sh writes both the block reports and
    # this request file into the same reports/<record-id>/ directory.
    return {
        "schema": "klt.gen_compose.request/1",
        "blocks": [
            {"id": bid, "generator_report": f"{bid}.json"}
            for bid in ("tail", "inpair", "latn", "latp", "rst")
        ],
        "placement": {
            "strategy": "row",
            "order": ["tail", "inpair", "latn", "latp", "rst"],
            "spacing_um": 3.0,
        },
        "connectivity": build_connectivity(),
        "routing": {
            "layer_role": "metal",
            "width_um": 0.3,
            "cross_block_layer_role": "metal2",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, required=True, help="path to write the request JSON to")
    args = parser.parse_args()

    request = build_request()
    args.output.write_text(json.dumps(request, indent=2) + "\n")
    total_pins = sum(len(e["pins"]) for e in request["connectivity"])
    print(
        f"build_compose_request.py: wrote {args.output} "
        f"({len(request['connectivity'])} nets, {total_pins} pins)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

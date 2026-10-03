#!/usr/bin/env python3
"""Generate every `klt gen` block DR-009's half-LSB quantizer-offset network
composes (issue #495): one `cap_array` matched pair for `Choff_n`/`Choff_p`
and six `mos_array` singles for `Moff_{n,p}_{cmn,refp,cmp}`.

The eight devices are the eight `sky130_fd_pr` primitives
`design/sar_adc_top.spice` instantiates at its own top level, inside no
sub-block, that had no drawn geometry anywhere under `layout/` before this
block existed. `layout/top-glue/` covers the 33 `sky130_fd_sc_hd` instances of
the same region; these eight are the non-standard-cell remainder (a MiM
capacitor and a hand-sized analog switch are not things `klt place-and-route`
can put on a `unithd` site grid).

Device sizing and connectivity here are **not** authored: they are a
transcription of `design/sar_adc_top.spice`'s own `XChoff_*`/`XMoff_*` cards,
and `bin/check-schematic-parity.py` re-derives them from that netlist on every
run and in CI, so a drift between this table and the schematic is a hard
failure rather than a thing a reader has to notice. Read that script's
docstring before editing anything below.

Why the table is built out of a role list and a per-side net map
---------------------------------------------------------------
DR-009 item 2 exists as a *pair*: `Choff_n` + three switches do the work, and
`Choff_p` + three identically-sized, tied-off switches are the matching dummy
whose only job is to put the same capacitance and the same switch junction
parasitics on the comparator's other input. That symmetry is the whole point
of the dummy, so this module does not write the two sides out twice and hope
they stay equal: `SWITCH_ROLES` fixes the role list (and with it the drawn
flavour, W, L and left-to-right floorplan slot, shared by both sides) and
`SWITCH_NETS` supplies only the part that legitimately differs -- which net
each terminal lands on. A side that drew a different device would have to
edit `SWITCH_ROLES`, where it is visibly shared.

`bin/build_layout.py` carries that through to geometry: the `_p` half is the
`_n` half translated by exactly `SIDE_PITCH_UM`, asserted shape-for-shape at
build time (see that module's `_assert_side_congruence`).

The capacitor: one `cap_array num=2` call, not two calls
-------------------------------------------------------
`Choff_n` and `Choff_p` are drawn as the two units of a single `klt gen
cap_array` invocation, the same choice `layout/sampling-frontend/bin/
gen_blocks.py` makes for its own two matched cap pairs: one generator call
emits two units of identical drawn geometry at one declared pitch, so their
equality is the generator's own property rather than something this module
re-derives twice.

`spacing_um` is derived from `SIDE_PITCH_UM` rather than chosen: setting the
cap pair's own unit pitch equal to the switch groups' translation makes ONE
translation vector relate the entire `_p` half of this network to the `_n`
half -- caps, switches, wells, taps and every per-pin via stack. See
`../README.md`, "One translation vector, and what it costs", for the tradeoff
that buys (congruent `BOT_OFF_N`/`BOT_OFF_P` routing) and what it costs (the
two caps sit ~13 um apart instead of abutting, so any linear process gradient
across that span is uncorrected -- and this block makes no matching
*measurement* claim either way).

No guard rings, same reason as every sibling: `mos_array`/`cap_array` do not
offer one and a closed `klt gen guard_ring` blocks routing to every port
inside it. Body ties come from `build_layout.py`'s own drawn n-well and
p-substrate taps.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _gen_common import add_klt_pdk_args, run_gen, write_and_check  # noqa: E402
from _pfet_devices import mos_array_params  # noqa: E402

#: The sub-block name this layout is compared under (`.SUBCKT` name on the
#: reference side, cell name of the deliverable GDS).
BLOCK_NAME = "halflsb_offset"

#: Every net this network touches, in the order the generated LVS reference
#: declares them as `.SUBCKT` pins -- and, checked by
#: `bin/check-schematic-parity.py`, exactly the set of nets
#: `design/sar_adc_top.spice`'s own eight cards name, so a net appearing or
#: disappearing in the schematic cannot go unnoticed here.
#:
#: Ten are real ports at the top level. `BOT_OFF_N`/`BOT_OFF_P` are internal to
#: this network -- see `build_layout.PIN_NETS` for why they are declared and
#: labelled anyway.
PORT_NETS = (
    "VDD",
    "GND",
    "VPWR",
    "VGND",
    "VREFP",
    "VCM",
    "HALF_LSB_EN",
    "HALF_LSB_ENN",
    "TOP_N",
    "TOP_P",
    "BOT_OFF_N",
    "BOT_OFF_P",
)

#: The two sides of DR-009 item 2, in floorplan order left to right. `"n"` is
#: the working half (the one that actually injects the half-LSB); `"p"` is the
#: matching dummy.
SIDES = ("n", "p")

#: Translation, in um, from the `_n` half of this network to the `_p` half.
#: Every block origin, well, tap and drawn shape below `TRACK_Y0` on the `_p`
#: side is its `_n` counterpart plus exactly `(SIDE_PITCH_UM, 0)` --
#: `build_layout.py` asserts it shape-for-shape rather than stating it.
#:
#: The value is set by the widest thing that has to fit inside one side's own
#: group (the n-well island holding that side's two PFETs, plus a channel to
#: the next side's p-substrate tap) and is checked from the actual generated
#: geometry on every build: `build_layout.py` raises if the group it lays out
#: does not fit, and if the `cap_array` unit pitch this value dictates is not
#: the pitch the generator reports.
SIDE_PITCH_UM = 16.00

#: The three switches each side carries, in left-to-right floorplan slot
#: order: `(role, drawn flavour, W um, L um)`.
#:
#: Flavours and sizes are DR-009's own ("device flavours and sizes copied from
#: the CDAC unit cell so the switch parasitics match a real array bit's") and
#: are identical between the two sides by construction -- only `SWITCH_NETS`
#: below differs. Slot order puts the single NFET first and the two PFETs
#: adjacent, which is what lets one n-well island per side hold both PFET
#: bodies without enclosing the NFET.
SWITCH_ROLES = (
    ("cmn", "nfet", 1.0, 0.15),
    ("refp", "pfet", 2.0, 0.15),
    ("cmp", "pfet", 2.0, 0.15),
)

#: `(role, side)` -> `(drain, gate, source, body)`, transcribed 1:1 from
#: `design/sar_adc_top.spice`'s own `XMoff_*` cards (an `X<name> D G S B
#: <model>` card names its terminals in that order):
#:
#:   XMoff_n_refp BOT_OFF_N HALF_LSB_EN  VREFP VDD  pfet_01v8 L=0.15 W=2
#:   XMoff_n_cmn  BOT_OFF_N HALF_LSB_EN  VCM   GND  nfet_01v8 L=0.15 W=1
#:   XMoff_n_cmp  BOT_OFF_N HALF_LSB_ENN VCM   VDD  pfet_01v8 L=0.15 W=2
#:   XMoff_p_refp BOT_OFF_P VGND         VREFP VDD  pfet_01v8 L=0.15 W=2
#:   XMoff_p_cmn  BOT_OFF_P VGND         VCM   GND  nfet_01v8 L=0.15 W=1
#:   XMoff_p_cmp  BOT_OFF_P VPWR         VCM   VDD  pfet_01v8 L=0.15 W=2
#:
#: The `_p` side's gates are tied off (`VGND` off, `VPWR` off) so `BOT_OFF_P`
#: sits at `VREFP` for the whole conversion and the dummy injects nothing --
#: DR-009's own wording. Note `VGND`/`VPWR` (the digital-domain supplies
#: DR-010 partitions) are NOT `GND`/`VDD` (the analog ones): they are four
#: distinct top-level ports, and this block draws four distinct conductors.
#: A parity-check failure naming one of them is a real defect, not a spelling.
SWITCH_NETS = {
    ("cmn", "n"): ("BOT_OFF_N", "HALF_LSB_EN", "VCM", "GND"),
    ("refp", "n"): ("BOT_OFF_N", "HALF_LSB_EN", "VREFP", "VDD"),
    ("cmp", "n"): ("BOT_OFF_N", "HALF_LSB_ENN", "VCM", "VDD"),
    ("cmn", "p"): ("BOT_OFF_P", "VGND", "VCM", "GND"),
    ("refp", "p"): ("BOT_OFF_P", "VGND", "VREFP", "VDD"),
    ("cmp", "p"): ("BOT_OFF_P", "VPWR", "VCM", "VDD"),
}

#: One row per drawn switch, derived (never hand-written) from the two tables
#: above: `(block id, schematic name, side, flavour, W um, L um, D, G, S, B)`.
#: Ordered side-major then slot, i.e. the order `build_layout.py` places them.
SWITCH_DEVICES = [
    (
        f"moff_{side}_{role}",
        f"Moff_{side}_{role}",
        side,
        flavor,
        w_um,
        l_um,
        *SWITCH_NETS[(role, side)],
    )
    for side in SIDES
    for role, flavor, w_um, l_um in SWITCH_ROLES
]

#: `klt gen` block id for the two-unit MiM pair.
CAP_BLOCK_ID = "choff"

#: The plate side `design/sar_adc_top.spice` asks for, verbatim from the
#: `XChoff_*` cards (`W=1.9000 L=1.9000`). Drawable exactly: 1.9000 um is
#: 1900 nm, legal on the 1 nm database grid AND on sky130's 5 nm
#: manufacturing grid.
#:
#: Was 1.8988 (1898.8 nm, off the 1 nm database grid) until
#: spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md
#: (#496) resized `C_u`, carried through here by #498.
CAP_SCHEMATIC_UM = 1.9000

#: The plate side actually drawn -- `layout/cdac-array/bin/cdac_layout.py`'s
#: own `CAPM_SIDE`, byte-identical on purpose and asserted against that file
#: by `bin/check-schematic-parity.py`.
#:
#: DR-009 sizes this cap "identical to `design/cdac/cdac_unit_cell.sch`'s
#: `C_u`", and the thing that has to be identical is the DRAWN plate, not the
#: schematic string: the half-LSB step is a *ratio* against one array bit, so
#: a 1 nm plate-side difference from the array's own units is a ratio error.
#: Before DR-019 that forced a choice -- round 1898.8 nm to the nearer grid
#: point (1899) or to the value the array already drew (1898)? -- and matching
#: the sibling won. DR-019 removes the choice entirely: the schematic value is
#: now itself grid-legal, so drawn == schematic == the array's own `CAPM_SIDE`,
#: with no rounding step anywhere.
CAP_DRAWN_UM = 1.900

#: `klt extract --deck sky130`'s own two-term MiM law, C = camimc*W*L +
#: cpmimc*2*(W+L) at the tt corner (area 2.0 fF/um^2, perimeter 0.19 fF/um),
#: evaluated on the DRAWN plate -- the same derivation
#: `layout/cdac-array/bin/cdac_layout.py` and
#: `layout/sampling-frontend/reference.spice` both use. Derived from drawn
#: geometry and the deck's published coefficients, never read back out of an
#: extraction result, so the generated LVS reference stays an independent
#: statement about the schematic.
CAP_AREA_F_UM2 = 2.0e-15
CAP_PERIM_F_UM = 1.9e-16
CAP_UNIT_F = CAP_DRAWN_UM**2 * CAP_AREA_F_UM2 + 4.0 * CAP_DRAWN_UM * CAP_PERIM_F_UM

#: The met3 bottom plate `klt gen cap_array` draws around a `plate_w_um`
#: capm square, as of the pinned `klt`: `plate_w_um` plus 0.5 um of met3
#: enclosure on each side. Needed *before* the generator runs, because the
#: `spacing_um` that makes the unit pitch come out at `SIDE_PITCH_UM` depends
#: on it -- so `build_layout.py` re-derives the achieved pitch from the
#: generator's own reported port positions and raises if it is not
#: `SIDE_PITCH_UM` exactly. A future `klt` that changes the enclosure fails
#: that assertion instead of silently shifting one side of the network.
CAP_MET3_ENCLOSURE_UM = 0.50
CAP_UNIT_W_UM = CAP_DRAWN_UM + 2 * CAP_MET3_ENCLOSURE_UM
CAP_SPACING_UM = SIDE_PITCH_UM - CAP_UNIT_W_UM

#: `(cap_array unit index, schematic name, side, top-plate net (`_TOP` port),
#: bottom-plate net (`_BOT` port))`.
#:
#: **The plate assignment is a layout decision, and it is this one**: the
#: comparator-side node (`TOP_N`/`TOP_P`) goes on the capm TOP plate and the
#: switched node (`BOT_OFF_N`/`BOT_OFF_P`) on the met3 BOTTOM plate. That is
#: `layout/cdac-array/`'s own convention for every one of its 1024 unit caps
#: (`C1 BOT TOP` in `reference/cdac_unit_cell.lvs-reference.spice`), and it is
#: the right way round physically: the top plate is the one further from the
#: substrate, so the sensitive high-impedance comparator input carries the
#: smaller plate-to-substrate parasitic. A `cap_mim_m3_1` SPICE card is
#: terminal-symmetric -- nothing in `design/sar_adc_top.spice` fixes which
#: node is drawn on which plate -- so the convention is declared here and
#: checked by `bin/check-schematic-parity.py` against the card's own node
#: order rather than left implicit.
CAP_LEGS = (
    (0, "Choff_n", "n", "TOP_N", "BOT_OFF_N"),
    (1, "Choff_p", "p", "TOP_P", "BOT_OFF_P"),
)


def cap_params() -> dict:
    """The `klt gen cap_array` parameter dict for the matched offset pair."""
    return {
        "plate_w_um": CAP_DRAWN_UM,
        "plate_h_um": CAP_DRAWN_UM,
        "num": 2,
        "spacing_um": CAP_SPACING_UM,
    }


def block_ids() -> list[str]:
    """Every `klt gen` block id this module emits, in emission order."""
    return [row[0] for row in SWITCH_DEVICES] + [CAP_BLOCK_ID]


def main() -> int:
    parser = add_klt_pdk_args(argparse.ArgumentParser(description=__doc__))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    ok = True

    for block_id, name, _side, flavor, w_um, l_um, *_nets in SWITCH_DEVICES:
        stdout, stderr = run_gen(
            args.klt,
            args.pdk,
            "mos_array",
            mos_array_params(flavor, w_um, l_um),
            name.upper(),
            args.out_dir / f"{block_id}.gds",
        )
        report = write_and_check(block_id, stdout, stderr, args.out_dir / f"{block_id}.json")
        ok = ok and report is not None
        if report:
            print(
                f"gen_blocks.py: {block_id} ({flavor} {w_um}/{l_um}um): "
                f"{report.get('device_count')} device"
            )

    stdout, stderr = run_gen(
        args.klt,
        args.pdk,
        "cap_array",
        cap_params(),
        CAP_BLOCK_ID.upper(),
        args.out_dir / f"{CAP_BLOCK_ID}.gds",
    )
    report = write_and_check(
        CAP_BLOCK_ID, stdout, stderr, args.out_dir / f"{CAP_BLOCK_ID}.json"
    )
    ok = ok and report is not None
    if report:
        print(
            f"gen_blocks.py: {CAP_BLOCK_ID} (cap_array "
            f"{CAP_DRAWN_UM}x{CAP_DRAWN_UM}um, num=2, spacing "
            f"{CAP_SPACING_UM}um): {report.get('device_count')} devices"
        )

    print(f"gen_blocks.py: generated {len(block_ids())} blocks in {args.out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

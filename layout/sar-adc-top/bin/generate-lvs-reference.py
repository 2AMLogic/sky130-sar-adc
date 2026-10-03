#!/usr/bin/env python3
"""Generate the top-level LVS reference for the SAR ADC assembly: each
composed sub-block's own already-generated, already-verified flat reference
subckt, concatenated, plus one `.SUBCKT sar_adc_top` wrapper instantiating all
six -- **derived from `design/sar_adc_top.spice` on every run, never written
by hand** (issues #387, #401).

Why the wrapper is generated rather than written
------------------------------------------------
Until issue #401 the wrapper was a string literal in this file, and it had
been wrong since 2026-09-11: it mirrored
`design/sar_adc_top.spice`'s `xfe`/`xcdac`/`xcmp`/`xseq`/`xinv_seln<i>` lines
**as they stood under issue #56**, which
`spec/decision-records/DR-008-cdac-top-level-switching-polarity.md` superseded.
Nothing caught it for two weeks of DRC/LVS-clean runs, because the layout it
was compared against had been composed from the SAME superseded glue -- so the
two sides of `klt lvs` agreed with each other whatever the schematic said.

A comment saying "keep this in sync" is what produced that. The fix is
mechanical, not editorial: every instance below, and every net on every one of
its pins, is read out of `design/sar_adc_top.spice` at generation time.
`design/sar_adc_top.spice` is itself gated against the schematic sources by
`design/regen_netlist.sh --check` in CI, so the chain is
schematic -> netlist -> this generator -> reference, with no self-reference.
`bin/check-composition-parity.py` (wired into `npm run check:ci`) then asserts
the same derivation holds for the *layout* side, headless and on every commit.

What this script does and does not derive
-----------------------------------------
It derives the **composition**: which sub-blocks exist, and which net lands on
each of their pins. It does NOT re-derive any sub-block's device-level
topology -- every sub-block device card comes unmodified from that block's own
committed reference, each of which `klt lvs` already verifies against its own
schematic in its own flow.

Three kinds of binding appear below, and only the first is a judgement call:

* **Layout-side-only ports** (`SUBBLOCK_EXTRA_PORTS`). Three of the four
  composed sub-block references expose ports their schematic `.subckt` does
  not: a `GND` the extraction deck's substrate synthesis makes real,
  `sampling_frontend`'s two internal boost nodes, and `sar_sequencer`'s two
  `.GLOBAL` supply rails. These are properties of how the LAYOUT reference was
  written, not of the schematic, so they are declared -- with the reason -- and
  asserted to be exactly the set of ports the derivation could not otherwise
  cover.
* **Positional ports.** Every port the schematic's own `.subckt` declares is
  zipped against the instance card's own positional net list. That is the
  binding that used to be hand-maintained and wrong.
* **Name-identical ports** (`top_glue`, `halflsb_offset`). Both of those
  blocks' references were themselves generated from these very cards, so each
  port name IS the schematic net name. The script asserts that -- the port set
  must equal the net set of the cards that block owns -- rather than assuming
  it.

Top-level primitive devices
---------------------------
DR-017's two per-domain decoupling capacitors are the only devices
`layout/sar-adc-top/` itself instantiates; the layout draws each `MF = 2` card
as two matched `klt gen cap_array` unit cells, so this side emits two cards per
domain to match device for device (`options.combine_devices` then folds each
parallel pair on both sides). Their value is computed from the card's own
`W`/`L` and the PDK's own MiM coefficients and cross-checked against
`build_layout.DECAP_UNIT_C_F`.

DR-009's eight top-level analog primitives and the 33 top-level
`sky130_fd_sc_hd` glue cells are no longer missing: since issue #401 they are
drawn by `layout/halflsb-offset/` and `layout/top-glue/` and enter this
reference as those blocks' own subckts.

Usage:
    layout/sar-adc-top/bin/generate-lvs-reference.py \\
        --sar-sequencer-report <dir> --top-glue-report <dir> \\
        --halflsb-offset-report <dir> -o <out.spice>

The three `--*-report` options name a `reports/<record-id>/` directory holding
that sub-block's own generated reference (those three flows mint one per run
rather than committing a stable top-level path, per their own READMEs).

Clean room: assembles this repo's own already-verified sub-block references
per this repo's own captured schematic; introduces no new device-level
content and consults no third-party netlist.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

PROG = "generate-lvs-reference.py"
BIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = BIN_DIR.parents[2]
LAYOUT_DIR = REPO_ROOT / "layout"

sys.path.insert(0, str(LAYOUT_DIR / "bin"))
sys.path.insert(0, str(LAYOUT_DIR / "halflsb-offset" / "bin"))

from _lvs_reference_common import top_level_subckt_body  # noqa: E402
from _schematic_cards import FOREIGN_INSTANCES, owned_cards  # noqa: E402

DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"

#: The sky130A MiM coefficients `klt extract --deck sky130` reports a
#: `cap_mim_m3_1` with, read out of the PDK's own
#: `libs.tech/ngspice/parameters/montecarlo.spice` at nominal `mim = 0`:
#: area 2.0 fF/um^2 (`camimc`), perimeter 0.19 fF/um (`cpmimc`). The same two
#: numbers `spec/decision-records/DR-017-*` computes its own per-domain
#: capacitance from, and the same ones `build_layout.DECAP_UNIT_C_F` asserts
#: against -- quoted once here so the reference's `C` cards, the composer's
#: placement arithmetic and the decision record cannot drift apart.
MIM_AREA_F_PER_UM2 = 2.0e-15
MIM_PERIM_F_PER_UM = 0.19e-15


class SubBlock(NamedTuple):
    """One composed sub-block: the schematic instance that specifies it, and
    the committed reference subckt the layout side is graded against."""

    instance: str  # the `x...` card in design/sar_adc_top.spice
    subckt: str  # the sub-block's own .subckt name
    emit_as: str  # instance name in the generated wrapper
    reference: str  # key into the resolved reference-path table
    note: str


#: The four sub-blocks whose pin binding is POSITIONAL -- each is instantiated
#: in `design/sar_adc_top.spice` by a card whose net list is zipped against
#: that sub-block's own `.subckt` port order, also read from the same file.
POSITIONAL_SUBBLOCKS = (
    SubBlock(
        "xfe",
        "sampling_frontend",
        "Xfe",
        "sampling_frontend",
        "bootstrapped input sampler (#99)",
    ),
    SubBlock("xcdac", "cdac_array", "Xcdac", "cdac_array", "10-bit split CDAC (#100)"),
    SubBlock(
        "xcmp", "comparator", "Xcmp", "comparator", "StrongARM latch comparator (#101)"
    ),
    SubBlock(
        "xseq",
        "sar_sequencer",
        "Xseq",
        "sar_sequencer",
        "walking-one ring + SAR register (#102)",
    ),
)

#: Ports each composed sub-block's LAYOUT reference declares that its
#: SCHEMATIC `.subckt` does not, and the net each must be tied to. This is the
#: one hand-maintained binding in this file, and it is deliberately about the
#: reference's own shape rather than about the design: a port that appears here
#: is one the positional derivation structurally cannot cover. `_bind()`
#: asserts the set is exactly right -- a reference port that is neither
#: positional nor listed here is fatal, and a listed port that the reference
#: does not actually declare is fatal too.
SUBBLOCK_EXTRA_PORTS = {
    "sampling_frontend": {
        # The sub-block's own reference promotes the substrate node to a port;
        # the schematic reaches it through `.GLOBAL GND`.
        "GND": "GND",
        # Two internal bootstrap nodes the sub-block's reference exposes so its
        # OWN flow can probe them. They are internal at this level and have no
        # schematic net, so they dead-end here.
        "BOOST_P": "BOOST_P_NC",
        "BOOST_N": "BOOST_N_NC",
    },
    "comparator": {"GND": "GND"},
    "sar_sequencer": {
        # `.GLOBAL VPWR` / `.GLOBAL VGND` in the schematic; real ports in the
        # place-and-routed macro's own reference. DR-010 keeps these separate
        # from the analog pair -- see that record, not this comment.
        "VPWR": "VPWR",
        "VGND": "VGND",
    },
}

#: The two blocks whose pin binding is BY NAME, because their own references
#: were generated from the very cards this script partitions: every port name
#: is the schematic net name. `_bind_by_name()` asserts that correspondence
#: against the cards rather than trusting it.
NAME_BOUND_BLOCKS = {
    "top_glue": "the 33 top-level sky130_fd_sc_hd glue cells (DR-008/DR-009)",
    "halflsb_offset": "DR-009's 8-primitive half-LSB offset network",
}

#: Nets that are `.GLOBAL` in `design/sar_adc_top.spice` and therefore never
#: appear on a standard cell's own supply pins as a *distinct* name. Used only
#: by `_bind_by_name()`'s coverage assertion.
GLOBAL_NETS = ("VPWR", "VGND", "VDD", "GND")

_SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$", re.M | re.I)
_PRIMITIVE_PREFIX = "sky130_fd_pr__"
_STD_CELL_PREFIX = "sky130_fd_sc_hd__"


def _die(message: str) -> None:
    raise SystemExit(f"{PROG}: {message}")


def _logical_lines(body: str) -> list[str]:
    """`body`'s instance cards, comments and `.`-directives stripped."""
    out = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        out.append(line)
    return out


def subckt_ports(spice_text: str) -> dict[str, list[str]]:
    """`{subckt_name: [port, ...]}` for every real `.subckt` in the dump.

    Continuation lines are not produced by `design/regen_netlist.sh`'s xschem
    dump (each `.subckt` is one line), and a surprise one would silently
    truncate a port list, so this asserts rather than guesses.
    """
    ports: dict[str, list[str]] = {}
    for match in _SUBCKT_RE.finditer(spice_text):
        name, rest = match.group(1), match.group(2)
        tail = spice_text[match.end() :].lstrip("\n")
        if tail.startswith("+"):
            _die(f".subckt {name} is continued on a '+' line, which this reader "
                 "does not handle -- extend it before relying on this output")
        ports[name] = rest.split()
    return ports


def reference_ports(path: Path) -> list[str]:
    """The `.SUBCKT` port list of a committed sub-block reference, including
    any `+` continuation lines (hand-written references do use them)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, raw in enumerate(lines):
        if not raw.strip().lower().startswith(".subckt"):
            continue
        tokens = raw.split()[2:]
        for cont in lines[i + 1 :]:
            if not cont.startswith("+"):
                break
            tokens.extend(cont[1:].split())
        return tokens
    _die(f"{path} has no .SUBCKT line")
    return []  # unreachable; keeps type checkers happy


def instance_cards(body: str) -> dict[str, list[str]]:
    """`{instance_name: [token, ...]}` for every `x`-prefixed card at the top
    level, keyed by the card's own instance name."""
    cards: dict[str, list[str]] = {}
    for line in _logical_lines(body):
        tokens = line.split()
        if not tokens[0][:1].lower() == "x":
            continue
        if tokens[0] in cards:
            _die(f"duplicate top-level instance name {tokens[0]}")
        cards[tokens[0]] = tokens
    return cards


def _bind(block: SubBlock, card: list[str], ports: list[str], ref_ports: list[str]) -> list[str]:
    """Net list for `block`, in its REFERENCE's own port order.

    Positional ports come from the schematic card; everything else must be
    declared in `SUBBLOCK_EXTRA_PORTS` with a reason.
    """
    nets = card[1:-1]
    if len(nets) != len(ports):
        _die(
            f"{block.instance}: {block.subckt} declares {len(ports)} ports but the "
            f"instance card names {len(nets)} nets"
        )
    binding = dict(zip(ports, nets))
    extra = SUBBLOCK_EXTRA_PORTS.get(block.subckt, {})
    unused = sorted(set(extra) - set(ref_ports))
    if unused:
        _die(
            f"{block.subckt}: SUBBLOCK_EXTRA_PORTS lists {unused}, which its own "
            f"reference ({', '.join(ref_ports)}) does not declare"
        )
    uncovered = [p for p in ref_ports if p not in binding and p not in extra]
    if uncovered:
        _die(
            f"{block.subckt}: reference port(s) {uncovered} are neither declared by "
            f"design/sar_adc_top.spice's own .subckt nor listed in "
            f"SUBBLOCK_EXTRA_PORTS -- add them there, with the reason, rather than "
            "letting this wrapper bind them by accident"
        )
    return [binding.get(port, extra.get(port, "")) for port in ref_ports]


def _owned_nets(cards: list[list[str]]) -> set[str]:
    """Every net named by a set of top-level SUBCIRCUIT instance cards (the
    model name is the last token, so the nets are everything between)."""
    nets: set[str] = set()
    for tokens in cards:
        nets.update(tokens[1:-1])
    return nets


def _net_owners(
    cards: dict[str, list[str]], std_cards: list[list[str]], owned: list
) -> dict[str, set[str]]:
    """`{net: {owner, ...}}` over every top-level card, where an owner is one
    of the two macro blocks or the literal card name of anything else.

    Used only to decide which of a macro's nets CROSS its boundary. A net
    named by nothing but that macro's own cards is internal to it; one that
    any other top-level card also names has to be routed at this level.
    """
    std_names = {t[0] for t in std_cards}
    owners: dict[str, set[str]] = {}
    for name, tokens in cards.items():
        if any(tok.startswith(_PRIMITIVE_PREFIX) for tok in tokens):
            # A `sky130_fd_pr` card's trailing tokens are parameters, not nets;
            # those cards are attributed from the parsed `Card`s below instead.
            continue
        owner = "top_glue" if name in std_names else name
        for net in tokens[1:-1]:
            owners.setdefault(net, set()).add(owner)
    offset_names = {card.name for card in owned}
    for card in owned:
        for net in card.nets:
            owners.setdefault(net, set()).add("halflsb_offset")
    for name, tokens in cards.items():
        if name in offset_names or not any(
            tok.startswith(_PRIMITIVE_PREFIX) for tok in tokens
        ):
            continue
        model_at = next(
            i for i, tok in enumerate(tokens) if tok.startswith(_PRIMITIVE_PREFIX)
        )
        for net in tokens[1:model_at]:
            owners.setdefault(net, set()).add(name)
    return owners


def _bind_by_name(
    block: str,
    ref_ports: list[str],
    owned_nets: set[str],
    net_owners: dict[str, set[str]],
    top_level_ports: set[str],
) -> list[str]:
    """Net list for a name-bound block: the port list itself, asserted against
    the schematic in both directions.

    * Every port must name a net the schematic actually puts on one of that
      block's own cards (so a stale port cannot bind to nothing).
    * Every net that **crosses the block's boundary** -- one the schematic also
      puts on a card this block does not own, or one that is a `sar_adc_top`
      port -- must have a port (so a net that has to be routed at the top level
      cannot silently become internal to the macro).

    A net named only by this block's own cards and by no top-level port is
    genuinely internal (`DOUT9N`, the nine `ADCOUT<i>` dead-ends, the two
    `DUMLOAD_*_NC` dead-ends, DR-009's `BOT_OFF_{N,P}`) and may be exposed or
    not -- that is the macro's own business, and neither choice changes what
    this composition has to route.
    """
    missing = sorted(set(ref_ports) - owned_nets - set(GLOBAL_NETS))
    if missing:
        _die(
            f"{block}: its reference declares port(s) {missing} that no card "
            "design/sar_adc_top.spice assigns to that block names -- the block's "
            "own layout has drifted from the schematic, or this script's "
            "ownership rule has"
        )
    crossing = {
        net
        for net in owned_nets
        if net in top_level_ports or net_owners.get(net, set()) - {block}
    }
    unreached = sorted(crossing - set(ref_ports) - set(GLOBAL_NETS))
    if unreached:
        _die(
            f"{block}: design/sar_adc_top.spice routes net(s) {unreached} across that "
            "block's boundary, but its reference exposes no port for them -- they "
            "would be silently internal to the macro"
        )
    return list(ref_ports)


def decap_cards(body: str) -> list[tuple[str, str, str, float, int]]:
    """DR-017's top-level decoupling capacitors, as
    `(instance, node_a, node_b, per_unit_F, units)`.

    Read off the schematic's own `MF`, so the number of unit cards this
    reference emits is the number the schematic asks for -- the layout draws
    `MF` matched unit cells per domain and `combine_devices` folds both sides.
    """
    from _schematic_cards import parse_primitive_cards  # noqa: PLC0415

    out = []
    for card in parse_primitive_cards(body, PROG):
        if card.name not in FOREIGN_INSTANCES:
            continue
        if card.flavour != "cap_mim":
            _die(f"{card.name}: expected a cap_mim decoupling card, got {card.flavour}")
        w, l = card.number("W"), card.number("L")
        units = int(card.number("MF"))
        per_unit = MIM_AREA_F_PER_UM2 * w * l + MIM_PERIM_F_PER_UM * 2.0 * (w + l)
        out.append((card.name, card.terminal("p1"), card.terminal("p2"), per_unit, units))
    return sorted(out)


def build_wrapper(spice_path: Path, refs: dict[str, Path]) -> tuple[str, dict[str, int]]:
    """The generated `.SUBCKT sar_adc_top` wrapper, plus a census for the
    caller to print."""
    text = spice_path.read_text(encoding="utf-8")
    body = top_level_subckt_body(text, PROG)
    ports = subckt_ports(text)
    cards = instance_cards(body)

    top_ports = re.search(r"^\*\*\.subckt\s+sar_adc_top\s+(.*)$", text, re.M)
    if top_ports is None:
        _die("no '**.subckt sar_adc_top' port line found")
    assert top_ports is not None

    lines = [f".SUBCKT sar_adc_top {' '.join(top_ports.group(1).split())}"]
    census = {"subblocks": 0, "std_cells": 0, "primitives": 0, "decaps": 0}

    for block in POSITIONAL_SUBBLOCKS:
        card = cards.get(block.instance)
        if card is None:
            _die(
                f"design/sar_adc_top.spice has no '{block.instance}' card -- this "
                "composition expects one instance of every sub-block it places"
            )
        if card[-1] != block.subckt:
            _die(
                f"{block.instance} instantiates {card[-1]!r}, not {block.subckt!r}"
            )
        ref_ports = reference_ports(refs[block.reference])
        nets = _bind(block, card, ports[block.subckt], ref_ports)
        lines.append(f"* {block.subckt} -- {block.note}")
        lines.append(
            f"* ports: {' '.join(ref_ports)}"
        )
        lines.append(_wrap_card(f"{block.emit_as} {' '.join(nets)} {block.subckt}"))
        census["subblocks"] += 1

    std_cards = [t for t in cards.values() if t[-1].startswith(_STD_CELL_PREFIX)]
    census["std_cells"] = len(std_cards)
    owned, _foreign = owned_cards(spice_path, PROG)
    census["primitives"] = len(owned)
    glue_net_set = _owned_nets(std_cards)
    offset_net_set = {net for card in owned for net in card.nets}
    net_owners = _net_owners(cards, std_cards, owned)
    top_level_ports = set(top_ports.group(1).split())

    glue_ports = reference_ports(refs["top_glue"])
    glue_nets = _bind_by_name(
        "top_glue", glue_ports, glue_net_set, net_owners, top_level_ports
    )
    lines.append(f"* top_glue -- {NAME_BOUND_BLOCKS['top_glue']}")
    lines.append(f"* ports: {' '.join(glue_ports)}")
    lines.append(_wrap_card(f"Xglue {' '.join(glue_nets)} top_glue"))

    offset_ports = reference_ports(refs["halflsb_offset"])
    offset_nets = _bind_by_name(
        "halflsb_offset",
        offset_ports,
        offset_net_set,
        net_owners,
        top_level_ports,
    )
    lines.append(f"* halflsb_offset -- {NAME_BOUND_BLOCKS['halflsb_offset']}")
    lines.append(f"* ports: {' '.join(offset_ports)}")
    lines.append(_wrap_card(f"Xhalflsb {' '.join(offset_nets)} halflsb_offset"))

    lines.append(
        "* On-die supply decoupling (DR-017): the only devices this assembly's own\n"
        "* top level instantiates. One card per unit cell the layout places, so the\n"
        "* two sides match device for device before combine_devices folds either."
    )
    for name, node_a, node_b, per_unit, units in decap_cards(body):
        census["decaps"] += units
        for unit in range(units):
            lines.append(
                f"{name[1:]}{unit} {node_a} {node_b} {per_unit:.6e} "
                "sky130_fd_pr__model__cap_mim"
            )
    lines.append(".ENDS")
    return "\n".join(lines) + "\n", census


def _wrap_card(card: str, width: int = 76) -> str:
    """A SPICE instance card, folded onto `\\`-free continuation lines."""
    tokens = card.split()
    out, line = [], tokens[0]
    for token in tokens[1:]:
        if len(line) + 1 + len(token) > width:
            out.append(line)
            line = "+ " + token
        else:
            line += " " + token
    out.append(line)
    return "\n".join(out)


def _check_decap_value(per_unit: float) -> None:
    """Cross-check the derived per-unit capacitance against the composer's own
    constant, so the reference and the placed geometry cannot disagree."""
    sys.path.insert(0, str(BIN_DIR))
    import build_layout as bl  # noqa: PLC0415

    if abs(per_unit - bl.DECAP_UNIT_C_F) > 1e-18:
        _die(
            f"derived decoupling unit capacitance {per_unit:.6e} F does not match "
            f"build_layout.DECAP_UNIT_C_F ({bl.DECAP_UNIT_C_F:.6e} F)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    parser.add_argument("--sar-sequencer-report", required=True, type=Path)
    parser.add_argument("--top-glue-report", required=True, type=Path)
    parser.add_argument("--halflsb-offset-report", required=True, type=Path)
    parser.add_argument("-o", "--out", required=True, type=Path)
    args = parser.parse_args()

    refs = {
        "sampling_frontend": LAYOUT_DIR / "sampling-frontend" / "reference.spice",
        "cdac_array": LAYOUT_DIR
        / "cdac-array"
        / "reference"
        / "cdac_array.lvs-reference.spice",
        "comparator": LAYOUT_DIR / "comparator" / "reference.spice",
        "sar_sequencer": args.sar_sequencer_report / "sar_sequencer.lvs-reference.spice",
        "top_glue": args.top_glue_report / "top_glue.lvs-reference.spice",
        "halflsb_offset": args.halflsb_offset_report / "reference.spice",
    }
    for name, path in refs.items():
        if not path.is_file():
            _die(f"{name}: no reference at {path}")

    wrapper, census = build_wrapper(args.spice, refs)
    body = top_level_subckt_body(args.spice.read_text(encoding="utf-8"), PROG)
    for *_rest, per_unit, _units in decap_cards(body):
        _check_decap_value(per_unit)

    parts = [
        "* sar_adc_top.lvs-reference.spice -- GENERATED, do not edit by hand.\n"
        "* Regenerate with: layout/sar-adc-top/bin/generate-lvs-reference.py\n"
        "* Assembles the six already-verified sub-block reference subckts\n"
        "* below (unmodified) into one hierarchical top-level netlist whose\n"
        "* composition is DERIVED from design/sar_adc_top.spice on every run\n"
        "* (issues #387/#401) -- see this script's own module docstring.\n\n"
    ]
    for name, path in refs.items():
        rel = path.resolve().relative_to(REPO_ROOT)
        parts.append(f"* --- from {rel} " + "-" * 20 + "\n")
        parts.append(path.read_text(encoding="utf-8"))
        parts.append("\n")
    parts.append(
        "* --- top-level composition, derived from design/sar_adc_top.spice "
        + "-" * 6
        + "\n"
    )
    parts.append(wrapper)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(parts), encoding="utf-8")
    print(
        f"{PROG}: wrote {args.out} -- {census['subblocks']} positional sub-blocks, "
        f"{census['std_cells']} std cells via top_glue, {census['primitives']} "
        f"primitives via halflsb_offset, {census['decaps']} decoupling unit cards"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

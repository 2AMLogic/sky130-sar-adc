"""Read DR-009's half-LSB offset network out of `design/sar_adc_top.spice`.

The **schematic side** of this block, and nothing else: a pure-text reader for
the top-level `sky130_fd_pr` instance cards, with no knowledge of what the
layout draws. `bin/check-schematic-parity.py` diffs what this module returns
against `bin/gen_blocks.py`'s layout-side table, and
`bin/generate-lvs-reference.py` derives the LVS reference from it. Keeping the
reader here -- rather than inside either of those -- is what keeps the two
sides of that diff from being the same file read twice.

Standard library only, no PDK, no `klt`: a `cap_mim_m3_1` / `{n,p}fet_01v8`
card is self-describing (`W`, `L`, `m`/`MF` are all on the card and the
terminal order of an `X<name> D G S B <model>` / `X<name> P1 P2 <model>` card
is fixed by the `sky130_fd_pr` symbols), so unlike
`layout/top-glue/bin/check-schematic-parity.py`'s standard cells there is no
`.SUBCKT` pin order to look up and no pin-order cache to keep fresh. That is
what lets the parity gate built on this run in CI's always-on headless job.

Ownership is decided from the SCHEMATIC side, not from a layout-side list
--------------------------------------------------------------------------
`design/sar_adc_top.spice`'s top level instantiates ten `sky130_fd_pr`
primitives, not eight: DR-009's offset network plus DR-017's two supply-domain
decoupling caps, which `layout/sar-adc-top/` draws. A parity check that simply
looked up the eight names it expected would be blind to an eleventh primitive
appearing at the top level -- which is precisely the drift class the whole gate
exists for.

So this module partitions every top-level `sky130_fd_pr` card into three sets
and makes the third one fatal:

* **owned** -- a card with a terminal on `BOT_OFF_N` or `BOT_OFF_P`, the two
  internal nodes DR-009's offset network is defined by. Structural, so a
  renamed device is still caught by its nets.
* **foreign** -- a card named in `FOREIGN_INSTANCES` below, each with the
  block that does draw it. An explicit, reviewable exception list.
* **residual** -- anything else. `owned_cards()` raises, naming the card, so a
  new top-level primitive has to be assigned an owner by a human rather than
  silently landing in nobody's layout (the state issues #387/#495 were filed
  to get out of).
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

#: The two internal nodes that define DR-009's offset network. A top-level
#: `sky130_fd_pr` card touching either one belongs to this block.
OWNING_NETS = ("BOT_OFF_N", "BOT_OFF_P")

#: Top-level `sky130_fd_pr` instances that are deliberately NOT this block's,
#: mapped to the block that draws them. Keep the reason, not just the name.
FOREIGN_INSTANCES = {
    "XCdecap_a": (
        "layout/sar-adc-top/ -- DR-017's analog-domain on-die decoupling cap "
        "(GND/VDD), drawn by that block's own build_layout.py"
    ),
    "XCdecap_d": (
        "layout/sar-adc-top/ -- DR-017's digital-domain on-die decoupling cap "
        "(VGND/VPWR), ditto"
    ),
}

#: `sky130_fd_pr` model name -> the device flavour `klt gen`/`klt extract`
#: speak. `klt extract --deck sky130` is a flat extractor that can only ever
#: report the generic class, so this is the vocabulary both sides share.
FLAVOUR_OF_MODEL = {
    "sky130_fd_pr__nfet_01v8": "nfet",
    "sky130_fd_pr__pfet_01v8": "pfet",
    "sky130_fd_pr__cap_mim_m3_1": "cap_mim",
}

#: Terminal names, in the positional order each flavour's card lists them.
#: A MOSFET card is `X<name> D G S B <model> ...`; a MiM cap card is
#: `X<name> P1 P2 <model> ...` -- P1/P2 being just terminals, since nothing in
#: the schematic decides which one is drawn on which plate (see
#: `gen_blocks.CAP_LEGS`, which declares that and is checked against this
#: order).
TERMINALS = {
    "nfet": ("d", "g", "s", "b"),
    "pfet": ("d", "g", "s", "b"),
    "cap_mim": ("p1", "p2"),
}

_PRIMITIVE_PREFIX = "sky130_fd_pr__"


class Card(NamedTuple):
    """One `sky130_fd_pr` instance card, parsed."""

    name: str
    model: str
    flavour: str
    nets: tuple[str, ...]
    params: dict[str, str]

    def terminal(self, which: str) -> str:
        """This card's net on terminal ``which`` (`d`/`g`/`s`/`b`, or
        `p1`/`p2` for a capacitor)."""
        return self.nets[TERMINALS[self.flavour].index(which)]

    def number(self, key: str) -> float:
        """A numeric parameter (`W`, `L`, `m`, `MF`, ...) as a float.

        Bare numbers only, which is what the `sky130_fd_pr` cards
        `design/regen_netlist.sh` writes carry -- no SPICE unit suffixes, no
        expressions. A value that is not a bare number raises rather than
        being coerced, since silently reading `W=2u` as 2 would compare a
        micron against a metre.
        """
        raw = self.params[key]
        return float(raw)


def parse_primitive_cards(body: str, prog: str) -> list[Card]:
    """Every `sky130_fd_pr` instance card in ``body``, in file order.

    ``body`` is a subcircuit body (see
    `layout/bin/_lvs_reference_common.py`'s `top_level_subckt_body()`).
    Unknown `sky130_fd_pr` models raise: this block's whole point is that an
    unmodelled primitive must not be quietly skipped.
    """
    cards: list[Card] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        tokens = line.split()
        model_index = next(
            (i for i, tok in enumerate(tokens) if tok.startswith(_PRIMITIVE_PREFIX)),
            None,
        )
        if model_index is None:
            continue
        model = tokens[model_index]
        if model not in FLAVOUR_OF_MODEL:
            raise SystemExit(
                f"{prog}: {tokens[0]}: unknown sky130_fd_pr model {model!r} -- "
                f"add it to _schematic_cards.FLAVOUR_OF_MODEL (and give it a "
                f"drawn counterpart) rather than letting it pass unchecked"
            )
        flavour = FLAVOUR_OF_MODEL[model]
        nets = tuple(tokens[1:model_index])
        if len(nets) != len(TERMINALS[flavour]):
            raise SystemExit(
                f"{prog}: {tokens[0]}: a {flavour} card names "
                f"{len(TERMINALS[flavour])} terminals, this one names {len(nets)}: "
                f"{list(nets)}"
            )
        params: dict[str, str] = {}
        for token in tokens[model_index + 1 :]:
            if "=" not in token:
                raise SystemExit(
                    f"{prog}: {tokens[0]}: unparsable parameter token {token!r}"
                )
            key, value = token.split("=", 1)
            params[key] = value
        cards.append(Card(tokens[0], model, flavour, nets, params))
    return cards


def partition(cards: list[Card]) -> tuple[list[Card], list[Card], list[Card]]:
    """Split ``cards`` into `(owned, foreign, residual)` -- see this module's
    docstring for the rule behind each."""
    owned, foreign, residual = [], [], []
    for card in cards:
        if any(net in OWNING_NETS for net in card.nets):
            owned.append(card)
        elif card.name in FOREIGN_INSTANCES:
            foreign.append(card)
        else:
            residual.append(card)
    return owned, foreign, residual


def owned_cards(spice_path: Path, prog: str) -> tuple[list[Card], list[Card]]:
    """`(owned, foreign)` for this block, or `SystemExit` on a residual card.

    Imports the top-level slicer from `layout/bin/_lvs_reference_common.py`
    lazily so this module stays importable without a `sys.path` insert of its
    own; every caller already inserts `layout/bin/`.
    """
    from _lvs_reference_common import top_level_subckt_body  # noqa: PLC0415

    body = top_level_subckt_body(spice_path.read_text(encoding="utf-8"), prog)
    owned, foreign, residual = partition(parse_primitive_cards(body, prog))
    if residual:
        listed = ", ".join(f"{card.name} ({card.model})" for card in residual)
        raise SystemExit(
            f"{prog}: {len(residual)} top-level sky130_fd_pr instance(s) belong "
            f"to no drawn block: {listed}.\n"
            f"  Every primitive design/sar_adc_top.spice adds at the top level "
            f"must be drawn somewhere under layout/ (that is the gap issues "
            f"#387 and #495 closed). Either it is part of DR-009's offset "
            f"network -- in which case it has a terminal on "
            f"{' or '.join(OWNING_NETS)} and this check would have claimed it "
            f"-- or it belongs to another block, in which case add it to "
            f"_schematic_cards.FOREIGN_INSTANCES naming that block."
        )
    return owned, foreign

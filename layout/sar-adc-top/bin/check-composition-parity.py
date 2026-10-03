#!/usr/bin/env python3
"""Assert that the top-level SAR ADC **composition** -- which sub-blocks are
placed, which net lands on each of their pins, and which nets reach a top-level
port -- is the composition `design/sar_adc_top.spice` specifies, on both sides
of `klt lvs` (issues #387, #401).

Why this gate exists
--------------------
Issue #387's finding was not a wrong number, it was a wrong *premise*: this
assembly composed `layout/seln-inverters/` and generated its LVS reference from
the same superseded instance list, so the two sides of `klt lvs` agreed with
each other for two weeks of DRC/LVS-clean runs while agreeing with nothing the
schematic said. No verdict this flow records could have caught that, because
both inputs to the verdict carried the same error.

`layout/top-glue/bin/check-schematic-parity.py` closed that class *inside* the
glue macro (its 33 instances, pin for pin) and
`layout/halflsb-offset/bin/check-schematic-parity.py` inside the offset network
(its 8 primitives, terminal for terminal). Neither looks at the **composition**:
both would stay green on an assembly that placed the right macros and wired them
to the wrong nets, or that left a net the schematic routes across a macro
boundary unrouted. This file is that missing third check.

What is checked
---------------
Everything below is derived from `design/sar_adc_top.spice`'s own top-level
cards. Nothing is a list of names this file expects to find.

1. **Card partition.** Every top-level card is attributed to exactly one placed
   block: the four named sub-block subckt calls (`xfe`/`xcdac`/`xcmp`/`xseq`),
   the `sky130_fd_sc_hd` bank (`top_glue`), DR-009's `sky130_fd_pr` offset
   network (`halflsb_offset`), or DR-017's two decoupling caps (drawn by this
   flow itself). A card that falls in none is fatal -- a new top-level instance
   has to be given an owner by a human, not land in nobody's layout.
2. **Block census, both directions.** The set of blocks `build_layout.OFFSETS`
   places is exactly the set step 1 derives. A retired block (`seln_inverters`)
   or a missing one fails here.
3. **Pin bindings.** For each positionally-bound sub-block, the schematic's own
   `.subckt` port order zipped against its instance card gives `(block, port) ->
   net`. Every `build_layout.PIN` entry for that block must name a port that
   binding has -- so a stale pin table entry cannot survive a schematic change.
4. **No unrouted crossing net.** A net with members in two or more placed
   blocks, or in one block plus a `sar_adc_top` port, must be routed at this
   level. Every such net must have a drawn member for each of its blocks --
   `build_layout.PIN`, `build_layout.MET5_STRAP` (the two digital rails, which
   are met5 PDN straps rather than DEF pins) or the name-bound macros' own
   track bands. A net the schematic routes across a boundary and this
   composition does not route is the defect class #387 is about, read from the
   other direction.
5. **Top-level ports.** The external pin labels `build_layout.build()` actually
   draws are exactly `**.subckt sar_adc_top`'s own port list -- no missing pin,
   no invented one.
6. **The generated LVS reference's own wrapper.** `bin/generate-lvs-reference.py`
   is run against the committed sub-block references and the emitted
   `.SUBCKT sar_adc_top` wrapper is diffed against the same schematic-derived
   binding: one instance per placed block, and each instance's net list equal to
   that block's own binding in its reference's port order. This is the half of
   #387 that was a string literal in that file, so it is asserted rather than
   reviewed.

Usage:
    layout/sar-adc-top/bin/check-composition-parity.py
    layout/sar-adc-top/bin/check-composition-parity.py --spice <path>
    layout/sar-adc-top/bin/check-composition-parity.py --self-test

`--self-test` is the negative control: it re-runs every check above against a
deliberately-corrupted copy of the netlist (one `SELp0` renamed on the gate that
drives it) and FAILS if the checks pass. A gate nobody has watched fail is a
gate nobody knows works -- the same falsifiability discipline
`docs/chipalooza/measure_metal_min_area.py --self-test` applies.

**Runs headless** -- pure text reads plus `build_layout`'s own pure-Python
geometry pass. No PDK, no `klt`, no `layout/.venv`, so it is wired into
`npm run check:ci` as `check:composition-parity` beside its two sibling gates.

Clean room: reads this repo's own schematic netlist and its own layout modules.
Consults no third-party netlist or layout.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType

BIN_DIR = Path(__file__).resolve().parent
TOP_DIR = BIN_DIR.parent
LAYOUT_DIR = TOP_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

# `layout/halflsb-offset/bin/` has a `build_layout.py` of its own, so this
# directory has to be inserted LAST (i.e. searched first) or `import
# build_layout` below silently binds the wrong block's composer.
sys.path.insert(0, str(LAYOUT_DIR / "halflsb-offset" / "bin"))
sys.path.insert(0, str(LAYOUT_DIR / "bin"))
sys.path.insert(0, str(BIN_DIR))

import build_layout as bl  # noqa: E402
from _lvs_reference_common import top_level_subckt_body  # noqa: E402
from _schematic_cards import FOREIGN_INSTANCES  # noqa: E402


def _load_hyphenated(path: Path) -> ModuleType:
    """Import a sibling script whose filename is not a legal module name.

    `bin/generate-lvs-reference.py` is a CLI entry point, not a library, so it
    is hyphenated like every other script in this directory. Check 6 has to run
    its ACTUAL wrapper builder rather than a copy of it -- a re-implementation
    here would be a second hand-maintained derivation, which is the thing this
    whole file exists to make impossible.
    """
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{PROG}: cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

PROG = "check-composition-parity.py"
DEFAULT_SPICE = REPO_ROOT / "design" / "sar_adc_top.spice"

#: This flow's own LVS-reference generator, imported for check 6.
glr = _load_hyphenated(BIN_DIR / "generate-lvs-reference.py")

#: Which placed block draws each top-level card class, and how its pins are
#: bound. `positional` means the schematic's own `.subckt` port order is zipped
#: against the instance card (the four sub-blocks); `by_name` means the macro's
#: own pin names ARE the schematic net names, which is true because both of
#: those macros' layouts were generated from these very cards and each has its
#: own parity gate asserting it (`npm run check:glue-parity`,
#: `check:halflsb-parity`).
POSITIONAL_BLOCKS = {
    "xfe": "sampling_frontend",
    "xcdac": "cdac_array",
    "xcmp": "comparator",
    "xseq": "sar_sequencer",
}
STD_CELL_BLOCK = "top_glue"
OFFSET_BLOCK = "halflsb_offset"

#: Blocks this composition places that are NOT instances in the schematic's own
#: top level: the four `klt gen cap_array` unit cells DR-017's two `MF = 2`
#: decoupling cards are drawn as. They are devices, not macros, so they take
#: part in the census (step 2) but have no pin binding to check.
DECAP_BLOCKS = frozenset(bl.DECAP_OFFSETS)

#: Blocks this composition USED to place and must not place again. Named rather
#: than merely absent: "the superseded glue is gone" is the single assertion
#: issue #387 exists for, and an empty check cannot state it.
RETIRED_BLOCKS = ("seln_inverters",)

#: Nets `.GLOBAL` in `design/sar_adc_top.spice`. A global reaches a sub-block's
#: supply pins without the top level naming it on that block's instance card, so
#: step 4 cannot require a positional binding for one.
GLOBAL_NETS = ("GND", "VDD", "VPWR", "VGND")

#: Ports a sub-block's own LAYOUT exposes that its schematic `.subckt` does not,
#: and so cannot be bound positionally. Deliberately a mirror of
#: `generate-lvs-reference.py`'s `SUBBLOCK_EXTRA_PORTS` -- read from there
#: rather than restated, so the two cannot drift.
LAYOUT_ONLY_PORTS = {
    block: frozenset(ports) for block, ports in glr.SUBBLOCK_EXTRA_PORTS.items()
}

#: `build_layout.PIN` entries that are this flow's own devices rather than a
#: sub-block port (the decap units' two generator-reported terminals).
DEVICE_PORTS = ("C0_BOT", "C0_TOP")

_STD_CELL_PREFIX = "sky130_fd_sc_hd__"
_PRIMITIVE_PREFIX = "sky130_fd_pr__"
_SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$", re.M | re.I)


# --------------------------------------------------------------------------- #
# The schematic side.
# --------------------------------------------------------------------------- #
class Composition:
    """`design/sar_adc_top.spice`'s own top level, partitioned by owner.

    Every attribute below is derived from the file. The point of the class is
    that there is exactly one derivation, used by every check and by nothing
    else -- `generate-lvs-reference.py`'s wrapper is then diffed against the
    same derivation rather than against a second reading of the same file.
    """

    def __init__(self, spice_path: Path) -> None:
        text = spice_path.read_text(encoding="utf-8")
        self.path = spice_path
        self.body = top_level_subckt_body(text, PROG)
        self.subckt_ports = {
            m.group(1): m.group(2).split() for m in _SUBCKT_RE.finditer(text)
        }
        top = re.search(r"^\*\*\.subckt\s+sar_adc_top\s+(.*)$", text, re.M)
        if top is None:
            raise SystemExit(f"{PROG}: no '**.subckt sar_adc_top' port line found")
        self.top_ports = tuple(top.group(1).split())

        self.problems: list[str] = []
        self.cards = self._cards()
        #: `{block: {port: net}}` for the four positionally-bound sub-blocks.
        self.bindings: dict[str, dict[str, str]] = {}
        #: `{block: {net, ...}}` for the two name-bound macros.
        self.macro_nets: dict[str, set[str]] = {}
        self._attribute()

    # -- parsing ---------------------------------------------------------- #
    def _cards(self) -> dict[str, list[str]]:
        cards: dict[str, list[str]] = {}
        for raw in self.body.splitlines():
            line = raw.strip()
            if not line or line.startswith("*") or line.startswith("."):
                continue
            tokens = line.split()
            # `top_level_subckt_body()` slices from the end of the literal
            # `**.subckt sar_adc_top`, so the body's first line is the REST of
            # that line -- the port list. Recognised by equality with the ports
            # parsed out of the same line, not by position, so a reader that
            # ever starts the slice elsewhere still skips exactly this.
            if tokens == list(self.top_ports):
                continue
            if tokens[0] in cards:
                raise SystemExit(f"{PROG}: duplicate top-level instance {tokens[0]}")
            cards[tokens[0]] = tokens
        return cards

    @staticmethod
    def _card_nets(tokens: list[str]) -> list[str]:
        """A card's nets. For a subckt call the model is the LAST token; for a
        `sky130_fd_pr` primitive the model is followed by parameters, so the
        nets are everything before the model."""
        for i, token in enumerate(tokens):
            if token.startswith(_PRIMITIVE_PREFIX):
                return tokens[1:i]
        return tokens[1:-1]

    def _attribute(self) -> None:
        """Check 1: give every top-level card an owner, or fail naming it."""
        for name, tokens in self.cards.items():
            nets = self._card_nets(tokens)
            if name in POSITIONAL_BLOCKS:
                block = POSITIONAL_BLOCKS[name]
                ports = self.subckt_ports.get(block)
                if ports is None:
                    self.problems.append(
                        f"{name} instantiates {block}, but no `.subckt {block}` "
                        f"appears in {self._rel()} -- nothing to bind its pins by"
                    )
                    continue
                if len(ports) != len(nets):
                    self.problems.append(
                        f"{name}: `.subckt {block}` declares {len(ports)} ports but "
                        f"the instance card names {len(nets)} nets"
                    )
                    continue
                self.bindings[block] = dict(zip(ports, nets))
            elif tokens[-1].startswith(_STD_CELL_PREFIX):
                self.macro_nets.setdefault(STD_CELL_BLOCK, set()).update(nets)
            elif any(t.startswith(_PRIMITIVE_PREFIX) for t in tokens):
                if name in FOREIGN_INSTANCES:
                    continue  # DR-017's decoupling caps -- drawn by this flow
                self.macro_nets.setdefault(OFFSET_BLOCK, set()).update(nets)
            else:
                self.problems.append(
                    f"top-level card {name} ({tokens[-1]}) belongs to no placed "
                    f"block -- give it an owner (a sub-block subckt call, the "
                    f"sky130_fd_sc_hd bank, DR-009's offset network, or "
                    f"_schematic_cards.FOREIGN_INSTANCES) rather than leaving it "
                    f"in nobody's layout"
                )

    def _rel(self) -> str:
        return os.path.relpath(self.path, REPO_ROOT)

    # -- derived views ---------------------------------------------------- #
    @property
    def blocks(self) -> set[str]:
        """Every block the schematic's own top level requires be placed."""
        return set(self.bindings) | set(self.macro_nets)

    def net_members(self) -> dict[str, set[str]]:
        """`{net: {owner, ...}}` over every placed block, where `owner` is the
        block id, plus the pseudo-owner `"(port)"` for a `sar_adc_top` port.

        This is what decides which nets THIS level has to route: a net owned by
        one block and nothing else is internal to that macro, and a net owned by
        two is a route this composition owes.
        """
        members: dict[str, set[str]] = {}
        for block, binding in self.bindings.items():
            for net in binding.values():
                members.setdefault(net, set()).add(block)
        for block, nets in self.macro_nets.items():
            for net in nets:
                members.setdefault(net, set()).add(block)
        for net in self.top_ports:
            members.setdefault(net, set()).add("(port)")
        return members


# --------------------------------------------------------------------------- #
# The layout side.
# --------------------------------------------------------------------------- #
def layout_pins() -> dict[str, set[str]]:
    """`{block: {port, ...}}` -- every sub-block pin `build_layout` has a
    coordinate for, plus the two digital rails it reaches by met5 strap merge
    rather than through a declared pin."""
    pins: dict[str, set[str]] = {}
    for block, port in bl.PIN:
        if port in DEVICE_PORTS:
            continue
        pins.setdefault(block, set()).add(port)
    for block, net in bl.MET5_STRAP:
        pins.setdefault(block, set()).add(net)
    return pins


def layout_external_labels() -> set[str]:
    """Every top-level pin label `build_layout.build()` draws.

    Taken from the geometry pass itself, not from a list: the labels are what
    `klt extract --pin-source-cells` promotes to this assembly's own pins, so
    this is the same set the LVS pin counts are measured against.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        draw_params, _compose, _measurements = bl.build()
    pin_layers = {
        tuple(layer)
        for layer in (bl.MET1_PIN, bl.MET2_PIN, bl.MET4_PIN, bl.MET5_PIN)
        if layer is not None
    }
    return {
        label["text"]
        for label in draw_params["labels"]
        if tuple(label["layer"]) in pin_layers
    }


# --------------------------------------------------------------------------- #
# The generated-reference side.
# --------------------------------------------------------------------------- #
def reference_paths() -> tuple[dict[str, Path], list[str]]:
    """The six committed sub-block references `bin/generate-lvs-reference.py`
    concatenates, resolved the way `bin/run-flow.sh` resolves them (three of
    them through their own flow's `reports/LATEST`).

    Returns `(paths, problems)`; a missing reference is reported rather than
    raised, so check 6 degrades to a named skip instead of taking the whole
    gate down on a checkout with no sub-block records.
    """

    def latest(block_dir: str, filename: str) -> Path:
        reports = LAYOUT_DIR / block_dir / "reports"
        record = (reports / "LATEST").read_text(encoding="utf-8").strip()
        return reports / record / filename

    problems: list[str] = []
    try:
        paths = {
            "sampling_frontend": LAYOUT_DIR / "sampling-frontend" / "reference.spice",
            "cdac_array": LAYOUT_DIR
            / "cdac-array"
            / "reference"
            / "cdac_array.lvs-reference.spice",
            "comparator": LAYOUT_DIR / "comparator" / "reference.spice",
            "sar_sequencer": latest(
                "sar-sequencer", "sar_sequencer.lvs-reference.spice"
            ),
            "top_glue": latest("top-glue", "top_glue.lvs-reference.spice"),
            "halflsb_offset": latest("halflsb-offset", "reference.spice"),
        }
    except OSError as exc:
        return {}, [f"could not resolve a sub-block reference: {exc}"]
    for name, path in paths.items():
        if not path.is_file():
            problems.append(f"{name}: no committed reference at {_rel(path)}")
    return paths, problems


def _rel(path: Path) -> str:
    return os.path.relpath(path, REPO_ROOT)


_WRAPPER_CARD_RE = re.compile(r"^(X\S+)\s+(.*)$")


def wrapper_instances(wrapper: str) -> dict[str, tuple[list[str], str]]:
    """`{instance: ([net, ...], subckt)}` for every subckt call in a generated
    `.SUBCKT sar_adc_top` wrapper, continuation lines folded back in."""
    instances: dict[str, tuple[list[str], str]] = {}
    logical: list[str] = []
    for raw in wrapper.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("*") or line.startswith("."):
            continue
        if line.startswith("+") and logical:
            logical[-1] += " " + line[1:].strip()
        else:
            logical.append(line)
    for line in logical:
        match = _WRAPPER_CARD_RE.match(line)
        if match is None:
            continue
        tokens = match.group(2).split()
        if len(tokens) < 2:
            continue
        instances[match.group(1)] = (tokens[:-1], tokens[-1])
    return instances


# --------------------------------------------------------------------------- #
# The checks.
# --------------------------------------------------------------------------- #
def compare(spice_path: Path) -> tuple[list[str], dict]:
    """`(problems, census)` -- every difference found, and what was compared."""
    comp = Composition(spice_path)
    problems = list(comp.problems)
    rel_spice = comp._rel()

    # --- 2. Block census, both directions ------------------------------- #
    placed = set(bl.OFFSETS) - DECAP_BLOCKS
    for block in sorted(comp.blocks - placed):
        problems.append(
            f"{rel_spice} requires block {block!r} at the top level, but "
            f"build_layout.OFFSETS does not place it"
        )
    for block in sorted(placed - comp.blocks):
        problems.append(
            f"build_layout.OFFSETS places block {block!r}, which no top-level "
            f"card in {rel_spice} needs -- the composition is drawing glue the "
            f"schematic does not have (issue #387's own failure mode)"
        )
    for block in RETIRED_BLOCKS:
        if block in bl.OFFSETS or block in bl.BBOX or block in bl.CELL_NAME:
            problems.append(
                f"retired block {block!r} is still referenced by build_layout's "
                f"placement tables -- DR-008 superseded it on 2026-09-11"
            )

    # --- 3. Pin bindings ------------------------------------------------ #
    pins = layout_pins()
    for block, binding in sorted(comp.bindings.items()):
        allowed = set(binding) | LAYOUT_ONLY_PORTS.get(block, frozenset())
        for port in sorted(pins.get(block, set()) - allowed):
            problems.append(
                f"build_layout.PIN has an entry for {block}.{port}, but neither "
                f"`.subckt {block}`'s own port list nor "
                f"generate-lvs-reference.SUBBLOCK_EXTRA_PORTS declares that port "
                f"-- a stale pin table entry"
            )
    for block in sorted(comp.macro_nets):
        for port in sorted(pins.get(block, set()) - comp.macro_nets[block] - set(GLOBAL_NETS)):
            problems.append(
                f"build_layout.PIN has an entry for {block}.{port}, but no "
                f"top-level card {rel_spice} assigns to that block names a net "
                f"{port!r} -- a stale pin table entry"
            )

    # --- 4. No unrouted crossing net ------------------------------------ #
    crossing = 0
    for net, owners in sorted(comp.net_members().items()):
        blocks = owners - {"(port)"}
        if len(owners) < 2:
            continue  # internal to one macro, or a port with no consumer
        crossing += 1
        if net in GLOBAL_NETS:
            # A global reaches each block's supply pins without the top level
            # naming it on the instance card, so there is no positional port to
            # look for. Its drawn members are graded by `klt erc` (one island
            # per supply) and by `bin/probe-ground-mesh.py`'s own ablation.
            continue
        for block in sorted(blocks):
            if block in comp.bindings:
                ports = [p for p, n in comp.bindings[block].items() if n == net]
                if not any(p in pins.get(block, set()) for p in ports):
                    problems.append(
                        f"net {net!r} crosses {block}'s boundary in {rel_spice} "
                        f"(on port(s) {', '.join(sorted(ports))}), but "
                        f"build_layout has no pin coordinate for any of them -- "
                        f"the composition leaves that net unrouted"
                    )
            elif net not in pins.get(block, set()):
                problems.append(
                    f"net {net!r} crosses {block}'s boundary in {rel_spice}, but "
                    f"build_layout has no pin coordinate for {block}.{net} -- the "
                    f"composition leaves that net unrouted"
                )

    # --- 5. Top-level ports --------------------------------------------- #
    drawn = layout_external_labels()
    declared = set(comp.top_ports)
    for net in sorted(declared - drawn):
        problems.append(
            f"{rel_spice} declares {net!r} a `sar_adc_top` port, but "
            f"build_layout draws no top-level pin label for it"
        )
    for net in sorted(drawn - declared):
        problems.append(
            f"build_layout draws a top-level pin label {net!r} that is not a "
            f"`sar_adc_top` port in {rel_spice}"
        )

    # --- 6. The generated LVS reference's own wrapper -------------------- #
    refs, ref_problems = reference_paths()
    problems.extend(ref_problems)
    wrapper_census = None
    if refs and not ref_problems:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                wrapper, wrapper_census = glr.build_wrapper(spice_path, refs)
        except SystemExit as raised:
            # The generator's own derivation refused this netlist. That IS a
            # finding, so it is reported alongside every other check rather than
            # taking this gate down with a traceback -- "print every difference,
            # not just the first" is the contract both sibling parity gates keep.
            problems.append(f"bin/generate-lvs-reference.py refused: {raised}")
            wrapper = ""
        instances = wrapper_instances(wrapper)
        emitted = {subckt for _nets, subckt in instances.values()}
        for block in sorted(comp.blocks - emitted):
            problems.append(
                f"the generated LVS reference's `.SUBCKT sar_adc_top` wrapper has "
                f"no instance of {block!r}, which {rel_spice} requires"
            )
        for block in sorted(emitted - comp.blocks):
            problems.append(
                f"the generated LVS reference's wrapper instantiates {block!r}, "
                f"which no top-level card in {rel_spice} needs"
            )
        for instance, (nets, subckt) in sorted(instances.items()):
            if subckt in comp.bindings:
                ref_ports = glr.reference_ports(refs[subckt])
                extra = glr.SUBBLOCK_EXTRA_PORTS.get(subckt, {})
                want = [
                    comp.bindings[subckt].get(port, extra.get(port))
                    for port in ref_ports
                ]
                if list(nets) != want:
                    problems.append(
                        f"wrapper instance {instance} ({subckt}) binds "
                        f"{nets} where {rel_spice}'s own positional binding gives "
                        f"{want}"
                    )
            elif subckt in comp.macro_nets:
                stale = [
                    n
                    for n in nets
                    if n not in comp.macro_nets[subckt] and n not in GLOBAL_NETS
                ]
                if stale:
                    problems.append(
                        f"wrapper instance {instance} ({subckt}) binds net(s) "
                        f"{stale}, which no top-level card {rel_spice} assigns to "
                        f"that block names"
                    )

    census = {
        "blocks": sorted(comp.blocks),
        "decap_cells": len(DECAP_BLOCKS),
        "cards": len(comp.cards),
        "positional_pins": sum(len(b) for b in comp.bindings.values()),
        "macro_nets": {block: len(nets) for block, nets in sorted(comp.macro_nets.items())},
        "crossing_nets": crossing,
        "top_ports": len(comp.top_ports),
        "wrapper": wrapper_census,
    }
    return problems, census


# --------------------------------------------------------------------------- #
# Negative control.
# --------------------------------------------------------------------------- #
#: The corruption `--self-test` injects: `xand_selp0`'s output net renamed, so
#: `cdac_array.SELp0` is driven by nothing and the gate's own output goes
#: nowhere. Chosen because it is exactly #387's shape -- a `SELp<i>` binding
#: that moved -- and because it is invisible to both sibling parity gates (the
#: instance list, cell types and pin order are all untouched).
SELF_TEST_FROM = (
    "xand_selp0 DOUT9 DOUT0 VGND VGND VPWR VPWR SELp0 sky130_fd_sc_hd__and2_1"
)
SELF_TEST_TO = (
    "xand_selp0 DOUT9 DOUT0 VGND VGND VPWR VPWR SELp0_MOVED "
    "sky130_fd_sc_hd__and2_1"
)


def self_test(spice_path: Path) -> int:
    """Run every check against a deliberately-corrupted netlist and require
    that they FAIL. Exit 0 only if the corruption was caught."""
    text = spice_path.read_text(encoding="utf-8")
    if SELF_TEST_FROM not in text:
        print(
            f"{PROG} --self-test: the card this control corrupts is no longer in "
            f"{_rel(spice_path)} verbatim:\n    {SELF_TEST_FROM}\n"
            "Update SELF_TEST_FROM/SELF_TEST_TO rather than dropping the control.",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / spice_path.name
        fixture.write_text(text.replace(SELF_TEST_FROM, SELF_TEST_TO), encoding="utf-8")
        try:
            problems, _census = compare(fixture)
        except SystemExit as raised:
            # A derivation that REFUSES the corrupted netlist outright (check 6
            # runs the real generator, which raises rather than returning) is a
            # caught corruption, not an error in this control.
            problems = [f"a derivation refused the fixture: {raised}"]
    if not problems:
        print(
            f"{PROG} --self-test: FAIL -- the corrupted netlist PASSED every "
            "check. This gate cannot see a moved SELp<i> binding, which is the "
            "exact drift issue #387 was filed for.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{PROG} --self-test: OK -- the negative control was caught "
        f"({len(problems)} problem(s)); first: {problems[0]}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spice", type=Path, default=DEFAULT_SPICE)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "negative control: run every check against a deliberately-corrupted "
            "copy of the netlist and fail unless the corruption is caught"
        ),
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test(args.spice)

    problems, census = compare(args.spice)
    rel_spice = os.path.relpath(args.spice, REPO_ROOT)

    if problems:
        print(
            f"{PROG}: FAIL -- layout/sar-adc-top/'s composition does not match "
            f"{rel_spice}'s own top level:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"{PROG}: OK -- {len(census['blocks'])} placed blocks "
        f"(+ {census['decap_cells']} decoupling unit cells) carrying "
        f"{census['cards']} top-level cards, {census['crossing_nets']} nets "
        f"crossing a block boundary and {census['top_ports']} top-level ports, "
        f"all derived from {rel_spice}"
    )
    print(f"  blocks: {', '.join(census['blocks'])}")
    for block, count in census["macro_nets"].items():
        print(f"  {block}: {count} nets named by its own cards")
    if census["wrapper"] is not None:
        wrapper = census["wrapper"]
        print(
            f"  generated LVS reference wrapper: {wrapper['subblocks']} positional "
            f"sub-blocks, {wrapper['std_cells']} std cells via {STD_CELL_BLOCK}, "
            f"{wrapper['primitives']} primitives via {OFFSET_BLOCK}, "
            f"{wrapper['decaps']} decoupling unit cards -- every net re-derived "
            f"from {rel_spice}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

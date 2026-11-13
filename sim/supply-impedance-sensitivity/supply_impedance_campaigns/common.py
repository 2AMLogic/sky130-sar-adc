"""Shared core of the supply-impedance-sensitivity campaigns.

Issue #848's behavior-preserving split of `run_supply_impedance.py`: this
module holds everything two or more of that runner's campaigns use -- the
DR-015 package-parasitic model, the `ARMS` table and its arm constructors,
deck assembly and patching, the cost probe, the restartable log cache, the
run loop and grid resolution, and the record-writer formatting helpers every
campaign's own writer shares.

`EXPERIMENT_DIR` has exactly one owner, here. Every other module reads it as
an attribute of this module (`common.EXPERIMENT_DIR`) rather than importing
the value, so that rebinding it on this module -- which the record-writer
tests do, to redirect a write into a temp directory -- redirects every
writer.

This module imports no campaign module; the campaign modules import this one.
"""
from __future__ import annotations

import functools
import json
import math
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: The experiment directory, `sim/supply-impedance-sensitivity/`. This module
#: sits one level deeper (inside the package), hence the second `.parent`.
EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
#: This runner's repo-relative path, as every record's `Written by` footer and
#: `sim/spec-coverage.json`'s bench index must spell it.
RUNNER_REL = "sim/supply-impedance-sensitivity/run_supply_impedance.py"
SIM_DIR = EXPERIMENT_DIR.parent
FULL_CONVERSION_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(FULL_CONVERSION_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

# The whole point of this campaign is to run the EXISTING full-conversion
# stimulus, so its driver is imported and reused (deck preamble constants,
# code/phase decoding, the committed fragment and its timing helpers) rather
# than re-derived here. Nothing in that module is modified by this one --
# it is under active, unrelated churn for issues #267/#269.
import run_conversion as fc  # noqa: E402

tb = fc.tb
REPO_ROOT = evidence.REPO_ROOT

NOMINAL_SUPPLY_V = fc.NOMINAL_SUPPLY_V
SUPPLY_TOLERANCE = fc.SUPPLY_TOLERANCE
TEMPS_C = fc.TEMPS_C
PROCESS_CORNERS = fc.PROCESS_CORNERS
BASELINE_CORNER = fc.BASELINE_CORNER


# --------------------------------------------------------------------------
# The package-style assumption (DR-015), derived rather than asserted
# --------------------------------------------------------------------------
# A short gold bond wire, as textbook round-wire geometry. Nothing here is a
# measurement of any package, and nothing here is anyone else's data: the
# inductance is the standard round-wire self-inductance expression and the
# resistance is rho*l/A for the same wire.
BOND_WIRE_LENGTH_MM = 1.5
BOND_WIRE_DIAMETER_UM = 25.4  # 1 mil, the common fine-wire size
GOLD_RESISTIVITY_OHM_M = 2.44e-8
MU0 = 4.0e-7 * math.pi

# Stated allowance for everything between the package pin and the board's
# star point (lead frame / ball + a short board trace). An allowance, not a
# derivation -- DR-015 records it as such.
LEAD_FRAME_L_NH = 0.5
LEAD_FRAME_R_MOHM = 30.0

# Lumped stand-in for the on-die / substrate return resistance. Magnitude
# from DR-012's own "10s of ohms" wording; NOT an extraction.
R_SUB_OHM = 30.0
# Lumped stand-in for the substrate path that makes `GND` and `VGND` one
# extracted net (DR-012's "GND and VGND are already ONE extracted net").
R_SUBX_OHM = 30.0


def bond_wire_inductance_h(length_mm: float, diameter_um: float) -> float:
    """Self-inductance of a straight round wire of length `l` and radius `r`:
    L = (mu0*l/2pi) * (ln(2l/r) - 3/4). Textbook low-frequency expression;
    the -3/4 is the uniform-current-distribution (DC) internal term."""
    length_m = length_mm * 1e-3
    radius_m = 0.5 * diameter_um * 1e-6
    return (MU0 * length_m / (2.0 * math.pi)) * (math.log(2.0 * length_m / radius_m) - 0.75)


def bond_wire_resistance_ohm(length_mm: float, diameter_um: float) -> float:
    area_m2 = math.pi * (0.5 * diameter_um * 1e-6) ** 2
    return GOLD_RESISTIVITY_OHM_M * (length_mm * 1e-3) / area_m2


BOND_L_H = bond_wire_inductance_h(BOND_WIRE_LENGTH_MM, BOND_WIRE_DIAMETER_UM)
BOND_R_OHM = bond_wire_resistance_ohm(BOND_WIRE_LENGTH_MM, BOND_WIRE_DIAMETER_UM)
PACKAGE_L_H = BOND_L_H + LEAD_FRAME_L_NH * 1e-9
PACKAGE_R_OHM = BOND_R_OHM + LEAD_FRAME_R_MOHM * 1e-3


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------
#: The DUT's analog-ground net, renamed at deck-assembly time (see
#: `run_supply_impedance.py`'s module docstring): a net named `GND` is
#: ngspice's global node 0 and cannot carry a series impedance.
GND_DIE = "GND_DIE"

#: terminal -> (die-side node, the fragment's own source card, source
#: instance name, board-side node name). `GND` has no source card in the
#: committed fragment at all -- this campaign adds one.
TERMINALS: dict[str, dict[str, str]] = {
    "VDD": {
        "die": "VDD",
        "card": "VVDD VDD 0 DC {vdd_val}",
        "source": "VVDD",
        "board": "VDD_BRD",
        "value": "{vdd_val}",
    },
    "VPWR": {
        "die": "VPWR",
        "card": "VVPWR VPWR 0 DC {vdd_val}",
        "source": "VVPWR",
        "board": "VPWR_BRD",
        "value": "{vdd_val}",
    },
    "VGND": {
        "die": "VGND",
        "card": "VVGND VGND 0 DC 0",
        "source": "VVGND",
        "board": "VGND_BRD",
        "value": "0",
    },
    "GND": {
        "die": GND_DIE,
        "card": "",  # added by this campaign, not present in the fragment
        "source": "VGNDA",
        "board": "GNDA_BRD",
        "value": "0",
    },
}

#: The four terminals, in the order DR-012 lists them.
TERMINAL_ORDER = ("VDD", "GND", "VPWR", "VGND")


@dataclass(frozen=True)
class Bond:
    """Series impedance between a board-side node and a die-side terminal."""

    r_ohm: float
    l_h: float

    def describe(self) -> str:
        return f"R = {self.r_ohm * 1e3:.1f} mOhm, L = {self.l_h * 1e9:.3f} nH"


#: `None` means "ideal": the source sits directly on the die node, no series
#: element at all. A terminal MISSING from an arm's `bonds` has no source and
#: no bond of its own -- it reaches the board only through `substrate` below.
IDEAL = None


@dataclass(frozen=True)
class Arm:
    name: str
    summary: str
    bonds: dict[str, Bond | None]
    #: extra lumped resistors, as (instance name, node a, node b, ohms)
    substrate: tuple[tuple[str, str, str, float], ...] = field(default=())
    #: MEASURED decoupling-tie interconnect resistance to insert between a
    #: rail's die node and one plate of one of the DUT's own decoupling
    #: capacitors, as `(cap instance, supply terminal, ohms)` triples (issue
    #: #465; see `DECAP_ESR_*` below). Empty on every named arm in `ARMS`, so
    #: their decks are byte-identical to what they were before this field
    #: existed -- only the synthesized `--decap-esr` ladder points carry it.
    decap_ties: tuple[tuple[str, str, float], ...] = field(default=())


def _pkg() -> Bond:
    return Bond(PACKAGE_R_OHM, PACKAGE_L_H)


def _pkg_r_only() -> Bond:
    """The `package` bond with its inductance removed and nothing else changed."""
    return Bond(PACKAGE_R_OHM, 0.0)


def _sub_r() -> Bond:
    return Bond(R_SUB_OHM, 0.0)


#: The substrate path that makes `GND` and `VGND` one extracted net
#: (DR-012). Present in EVERY arm so the four decks differ only in their
#: bond impedances; in `ideal` both of its ends are held at 0 V by ideal
#: sources, so it carries no current and the arm stays a clean control.
_SUBSTRATE_LINK = (("RSUBX", GND_DIE, "VGND", R_SUBX_OHM),)


ARMS: tuple[Arm, ...] = (
    Arm(
        name="ideal",
        summary=(
            "every supply terminal driven by an ideal source at the die node "
            "(the zero-impedance control every existing sim/ campaign runs today)"
        ),
        bonds={"VDD": IDEAL, "GND": IDEAL, "VPWR": IDEAL, "VGND": IDEAL},
        substrate=_SUBSTRATE_LINK,
    ),
    Arm(
        name="package-r-only",
        summary=(
            "all four terminals bonded through the DR-015 package RESISTANCE with "
            "L = 0 -- the strict one-element ablation of `package` below, so the "
            "difference between the two is the bond inductance and nothing else"
        ),
        bonds={
            "VDD": _pkg_r_only(),
            "GND": _pkg_r_only(),
            "VPWR": _pkg_r_only(),
            "VGND": _pkg_r_only(),
        },
        substrate=_SUBSTRATE_LINK,
    ),
    Arm(
        name="package",
        summary=(
            "all four terminals bonded through the DR-015 package R+L "
            "(DR-012's as-built shape: four drawn pads, star point off-die)"
        ),
        bonds={"VDD": _pkg(), "GND": _pkg(), "VPWR": _pkg(), "VGND": _pkg()},
        substrate=_SUBSTRATE_LINK,
    ),
    Arm(
        name="substrate",
        summary=(
            "no bond inductance anywhere: a lumped resistance of the SUBSTRATE's "
            "own order (R_SUB, tens of ohms) in the two ground returns only -- the "
            "on-die-only resistive return, not an ablation of `package` (its "
            "resistance is ~300x the package R)"
        ),
        bonds={"VDD": IDEAL, "GND": _sub_r(), "VPWR": IDEAL, "VGND": _sub_r()},
        substrate=_SUBSTRATE_LINK,
    ),
    Arm(
        name="no-gnd-pad",
        summary=(
            "DR-012's rejected null option: GND has no bond of its own and "
            "reaches the board only through the lumped substrate resistance to "
            "VGND's die node; VDD/VPWR/VGND keep their package R+L"
        ),
        bonds={"VDD": _pkg(), "VPWR": _pkg(), "VGND": _pkg()},
        substrate=_SUBSTRATE_LINK,
    ),
)

ARMS_BY_NAME = {arm.name: arm for arm in ARMS}
CONTROL_ARM = "ideal"

#: Why a record that does NOT contain an arm is still a valid record.
#:
#: `sim/README.md` requires a corner subset to be justified; an arm subset is
#: the same kind of omission and gets the same treatment, so every arm the
#: runner offers has a standing reason a record may state when it leaves that
#: arm out. These are properties of the ARM (what it is for, and what a record
#: without it therefore cannot say), not of any one run -- a record-specific
#: reason belongs in that record's own prose, not in a constant here.
ARM_OMISSION_NOTES: dict[str, str] = {
    "package-r-only": (
        "the `L = 0` twin of `package`. A record without it has no "
        "**bond-inductance ablation** -- that number is the difference between "
        "these two arms and cannot be reconstructed from either one alone -- so "
        "such a record may compare whole grounding schemes but may not attribute "
        "a difference to the series `L`."
    ),
    "package": (
        "the as-built shape DR-012 chose (four drawn pads, star point off-die). "
        "A record without it has no as-built row, so nothing in it is a statement "
        "about what this block's own ground plan costs."
    ),
    "substrate": (
        "an **on-die-only** resistive return of DR-012's stated order. It answers "
        "a different question from the bonded arms rather than ablating them (its "
        "resistance is ~300x the package R), so a record without it is not missing "
        "a term in any comparison the other arms make -- it simply does not ask "
        "that question."
    ),
    "no-gnd-pad": (
        "DR-012's rejected null option. Paired with `package` it is the one pair "
        "that prices DR-012's rejected alternative against the option DR-012 chose, "
        "so a record without it says nothing about what the null option would have "
        "cost. Omitting it was for a long time called a **cost** decision, on a "
        "truncated-slice projection of roughly an order of magnitude and 'several "
        "hours' per run; the full run measured **1.67x the control** -- cheaper "
        "than the `package` arm beside it. A record that leaves this arm out may "
        "therefore state the arm's *scope* as its reason (it asks a different "
        "question from the bonded ladder) but may no longer plead its price."
    ),
}
SWEEP_BASE_ARM = "package"

#: The committed layout record whose `decap-ties.json` this ladder reads its
#: resistances out of (issue #440's placement pass). Pinned by id, not resolved
#: through `reports/LATEST`, because a record is append-only evidence and the
#: resistance a simulation was run at must stay legible after a later layout
#: record moves that pointer. Bumping this constant is how a re-drawn tie
#: reaches this campaign.
DECAP_TIE_RECORD = "layout/sar-adc-top/reports/20260926-081248-203cca3"

#: The DUT's own decoupling capacitors (DR-017), as
#: `(instance, domain key in decap-ties.json's per_domain, the supply terminals
#: its two plates tie to IN THE CARD'S OWN NODE ORDER)`. The node order is part
#: of the contract: `patch_dut_decap_ties()` asserts the committed card still
#: connects those two nets in that order and refuses to patch a netlist whose
#: shape has moved, rather than silently inserting the analog return's
#: resistance into the supply leg.
DECAP_DEVICES: tuple[tuple[str, str, tuple[str, str]], ...] = (
    ("XCdecap_a", "analog (VDD/GND)", ("GND", "VDD")),
    ("XCdecap_d", "digital (VPWR/VGND)", ("VGND", "VPWR")),
)

#: The device this campaign expects to find on a decoupling card. Asserted so a
#: future netlist that swaps the decoupling device for something else fails here
#: instead of being silently re-tied.
DECAP_DEVICE_MODEL = "sky130_fd_pr__cap_mim"


def _decap_node(instance: str, terminal: str) -> str:
    """The internal node between a tie resistor and the capacitor's own plate."""
    return f"{instance.lstrip('Xx').upper()}_{terminal}"


def _decap_tie_instance(instance: str, terminal: str) -> str:
    return f"RTIE_{instance.lstrip('Xx').upper()}_{terminal}"


# --------------------------------------------------------------------------
# Extra measurements this campaign adds on top of the committed fragment
# --------------------------------------------------------------------------
def _idd_window_ns() -> tuple[float, float]:
    """The same steady-state conversion the committed fragment averages its
    supply currents over (conversion `tb.IDD_CONVERSION`, all 12 CLK
    periods) -- so every number in this record shares one window."""
    t0 = tb.t_edge_ns(tb.PHASES_PER_CONVERSION * tb.IDD_CONVERSION)
    t1 = tb.t_edge_ns(tb.PHASES_PER_CONVERSION * (tb.IDD_CONVERSION + 1))
    return t0, t1


#: (measurement name, node, human label) for the die-side rail excursions.
RAIL_PROBES: tuple[tuple[str, str, str], ...] = (
    ("gnd_die", GND_DIE, "analog ground (`GND`, the comparator's own reference)"),
    ("vgnd_die", "VGND", "digital ground (`VGND`)"),
    ("vdd_die", "VDD", "analog supply (`VDD`)"),
    ("vpwr_die", "VPWR", "digital supply (`VPWR`)"),
)


def extra_measure_lines(arm: Arm) -> list[str]:
    t0, t1 = _idd_window_ns()
    lines = [
        "",
        "* --- issue #378: die-side rail excursion over the same steady-state",
        f"* conversion the fragment averages its supply currents over "
        f"({t0:.4f} ns to {t1:.4f} ns).",
    ]
    for name, node, _label in RAIL_PROBES:
        lines.append(f".meas tran {name}_pp pp v({node}) from={t0:.4f}n to={t1:.4f}n")
        lines.append(f".meas tran {name}_max max v({node}) from={t0:.4f}n to={t1:.4f}n")
        lines.append(f".meas tran {name}_min min v({node}) from={t0:.4f}n to={t1:.4f}n")
    if "GND" in arm.bonds:
        lines.append(
            f".meas tran i_gnda avg i({TERMINALS['GND']['source'].lower()}) "
            f"from={t0:.4f}n to={t1:.4f}n"
        )
    return lines


def extra_measure_names(arm: Arm) -> list[str]:
    names: list[str] = []
    for name, _node, _label in RAIL_PROBES:
        names += [f"{name}_pp", f"{name}_max", f"{name}_min"]
    if "GND" in arm.bonds:
        names.append("i_gnda")
    return names


# --------------------------------------------------------------------------
# Deck assembly
# --------------------------------------------------------------------------
_GND_TOKEN_RE = re.compile(r"(?<![\w.$])GND(?![\w.$])", re.IGNORECASE)


def patch_dut_ground(dut_netlist_text: str) -> tuple[str, int]:
    """Rename the DUT's `GND` net to `GND_DIE` on every device/instance card.

    ngspice aliases a node named `gnd` onto the global ground node `0`, so
    without this rename every series element this campaign inserts in the
    analog-ground return would be shorted out and the campaign would silently
    measure the ideal case four times. Comment lines are left alone (they are
    the netlister's port-declaration record, not connectivity), but the
    top-level port declaration is asserted to still name `GND` -- if
    `design/sar_adc_top.spice` ever stops declaring that port, DR-012's
    subject has changed and this campaign must be re-derived rather than
    quietly running against a different interface.
    """
    if not re.search(r"^\*\*\.subckt\s+sar_adc_top\b.*\bGND\b", dut_netlist_text, re.MULTILINE):
        raise RuntimeError(
            "design/sar_adc_top.spice no longer declares a top-level `GND` port "
            "(DR-012's interface) -- re-derive this campaign before running it."
        )

    out: list[str] = []
    hits = 0
    for line in dut_netlist_text.splitlines():
        if line.lstrip().startswith("*") or line.strip().lower() == ".end":
            if line.strip().lower() != ".end":
                out.append(line)
            continue
        patched, n = _GND_TOKEN_RE.subn(GND_DIE, line)
        hits += n
        out.append(patched)
    if hits < 1:
        raise RuntimeError(
            "no `GND` net reference found on any device card of "
            "design/sar_adc_top.spice -- the netlist changed shape; re-derive "
            "this campaign's ground rename."
        )
    return "\n".join(out), hits


def patch_dut_decap_ties(dut_body: str, arm: Arm) -> tuple[str, list[str]]:
    """Insert this arm's measured decoupling-tie resistance into the DUT body.

    The THIRD testbench-only transformation of this campaign (issue #465), and
    the only one that touches a device card rather than a net name or a source
    card. For each `(cap instance, supply terminal, ohms)` triple the arm
    carries, the capacitor's own plate node is re-pointed to a new internal node
    and a resistor is emitted from the rail's die node to it -- so the rail still
    sees the capacitor, through the resistance the layout actually drew.

    Returns `(patched body, the resistor cards)`. An arm with no triples gets
    the body back UNCHANGED and no cards, which is what makes the ladder's `0x`
    rung and every named arm byte-identical to the deck they assembled before
    this transformation existed.

    Every shape assumption is asserted rather than assumed, for the same reason
    `patch_dut_ground()` asserts the port declaration: a netlist that moved would
    otherwise be re-tied silently, and a resistor inserted into the wrong leg
    would produce a plausible record of a circuit nobody built.
    """
    if not arm.decap_ties:
        return dut_body, []

    wanted: dict[str, dict[str, float]] = {}
    for instance, terminal, ohms in arm.decap_ties:
        wanted.setdefault(instance, {})[terminal] = ohms

    text = dut_body
    cards: list[str] = []
    for instance, domain, terminals in DECAP_DEVICES:
        per_terminal = wanted.pop(instance, None)
        if per_terminal is None:
            continue
        pattern = re.compile(rf"(?m)^{re.escape(instance)}[ \t]+(\S+)[ \t]+(\S+)[ \t]+(\S.*)$")
        found = pattern.findall(text)
        if len(found) != 1:
            raise RuntimeError(
                f"expected exactly one `{instance}` card in design/sar_adc_top.spice, "
                f"found {len(found)} -- DR-017's {domain} decoupling capacitor is not "
                "where this campaign's tie model says it is; re-derive the "
                "decoupling-tie ladder before running it."
            )
        node_a, node_b, tail = found[0]
        if DECAP_DEVICE_MODEL not in tail:
            raise RuntimeError(
                f"`{instance}` is no longer a `{DECAP_DEVICE_MODEL}*` device "
                f"({tail.split()[0]!r}) -- the decoupling device changed; re-derive "
                "the decoupling-tie ladder rather than re-tying an unknown element."
            )
        expected = tuple(TERMINALS[t]["die"] for t in terminals)
        if (node_a, node_b) != expected:
            raise RuntimeError(
                f"`{instance}` connects ({node_a}, {node_b}), not the expected "
                f"{expected} for the {domain} domain -- its plate order or its rails "
                "moved, and inserting a measured tie resistance into the wrong leg "
                "would misstate which path carries it; re-derive the ladder."
            )
        new_nodes: list[str] = []
        for terminal, node in zip(terminals, (node_a, node_b)):
            ohms = per_terminal.get(terminal)
            if ohms is None:
                new_nodes.append(node)
                continue
            internal = _decap_node(instance, terminal)
            new_nodes.append(internal)
            cards.append(f"{_decap_tie_instance(instance, terminal)} {node} {internal} {ohms:.6e}")
        text = pattern.sub(
            lambda m, new=new_nodes: f"{instance} {new[0]} {new[1]} {m.group(3)}",
            text,
            count=1,
        )
    if wanted:
        raise RuntimeError(
            f"arm `{arm.name}` carries tie resistance for capacitor instance(s) "
            f"{sorted(wanted)}, which are not in this campaign's DECAP_DEVICES table"
        )
    return text, cards


def decap_tie_comment_lines(arm: Arm, ties_record: str) -> list[str]:
    """The header comment the measured tie resistors are emitted under."""
    if not arm.decap_ties:
        return []
    return [
        "* --- issue #465: MEASURED decoupling-tie interconnect resistance ---------",
        f"* From {ties_record}/decap-ties.json (issue #440's probe): a lumped DC",
        "* ladder over the DRAWN straps/vias, from the PDK's own sheet/via",
        "* resistances. No interconnect INDUCTANCE is modelled (out of scope).",
    ]


def check_pdk_has_no_bare_gnd_node(pdk_info: pdk.PdkInfo) -> list[str]:
    """Assert the PDK itself never names a node `GND`.

    `patch_dut_ground()` renames the DUT's own analog ground, but the assembled
    deck also pulls in two bodies of SPICE this campaign does NOT rewrite: the
    `sky130_fd_sc_hd` combined cell deck it `.include`s, and the device model
    library the `.lib` card selects. If either ever named a node `GND`, ngspice
    would alias that node onto global `0` and those devices would reach ground
    without passing through this campaign's series network -- silently, with a
    perfectly clean log and a plausible record, and the campaign would understate
    every effect it exists to measure.

    At `sim/pdk.json`'s pinned open_pdks commit both are clean (the standard
    cells use `VGND`/`VNB`, and the models take their bulk from a port), which is
    why this is a cheap guard rather than a problem. It is checked rather than
    trusted because it is a property of the PDK, not of this repo, and a pin bump
    could change it without anything else here moving.

    Returns the offending `path:line` strings, empty when clean.
    """
    roots = [
        pdk_info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice",
        pdk_info.variant_dir / "libs.tech" / "ngspice",
    ]
    offenders: list[str] = []
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("*") or stripped.startswith(";") or not stripped:
                continue
            if _GND_TOKEN_RE.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()[:120]}")
                if len(offenders) >= 5:
                    return offenders
    return offenders


def patch_fragment_supplies(fragment_text: str, arm: Arm) -> str:
    """Re-point the committed fragment's own supply source cards at their
    board-side nodes for every terminal this arm bonds through an impedance.

    The source INSTANCE names are unchanged, so the fragment's own
    `.meas tran i_vdd avg i(vvdd)` cards still measure the current delivered
    from the board. Every other line of the fragment -- the `.tran` card, the
    clock, the reset, the input schedule, all 300+ code/phase `.meas` cards
    -- is used verbatim.
    """
    text = fragment_text
    for terminal in ("VDD", "VPWR", "VGND"):
        spec = TERMINALS[terminal]
        bond = arm.bonds.get(terminal, IDEAL)
        if bond is None:
            continue  # ideal: the source stays on the die node
        old = spec["card"]
        new = old.replace(f" {spec['die']} 0 ", f" {spec['board']} 0 ", 1)
        if text.count(old) != 1:
            raise RuntimeError(
                f"expected exactly one `{old}` card in the committed fragment, "
                f"found {text.count(old)} -- the fragment changed shape; "
                "re-derive this campaign's supply re-pointing."
            )
        text = text.replace(old, new, 1)
    return text


def arm_network_lines(arm: Arm) -> list[str]:
    """The arm's own source/bond/substrate cards."""
    lines = [
        "* --- issue #378 supply-return network ---------------------------------",
        f"* arm `{arm.name}`: {arm.summary}",
    ]
    for terminal in TERMINAL_ORDER:
        spec = TERMINALS[terminal]
        if terminal not in arm.bonds:
            lines.append(
                f"* {terminal}: no bond of its own (reaches the board only through "
                "the substrate network below)"
            )
            continue
        bond = arm.bonds[terminal]
        if terminal == "GND":
            # The committed fragment has no GND source at all; add one here.
            node = spec["die"] if bond is None else spec["board"]
            lines.append(f"{spec['source']} {node} 0 DC {spec['value']}")
        if bond is None:
            lines.append(f"* {terminal}: ideal source at the die node ({spec['die']})")
            continue
        if bond.l_h > 0.0:
            mid = f"{spec['board']}_M"
            lines.append(f"L{terminal} {spec['board']} {mid} {bond.l_h:.6e}")
            lines.append(f"R{terminal} {mid} {spec['die']} {bond.r_ohm:.6e}")
        else:
            # A resistance-only bond: emitting a zero-valued inductor instead
            # would be a different (degenerate) element, not a simpler one.
            lines.append(f"R{terminal} {spec['board']} {spec['die']} {bond.r_ohm:.6e}")
    for name, node_a, node_b, ohms in arm.substrate:
        lines.append(f"{name} {node_a} {node_b} {ohms:.6e}")
    lines.append("")
    return lines


def assemble_deck(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    arm: Arm,
    process_corner: str,
    temp_c: float,
    supply_v: float,
) -> str:
    stdcell_spice = (
        pdk_info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    )
    if not stdcell_spice.is_file():
        raise RuntimeError(f"sky130_fd_sc_hd combined SPICE deck not found at {stdcell_spice}")

    dut_body, _hits = patch_dut_ground(dut_netlist_text)
    dut_body, decap_tie_cards = patch_dut_decap_ties(dut_body, arm)
    fragment = patch_fragment_supplies(tb.FRAGMENT_PATH.read_text(), arm)

    lines = [
        "* sim/supply-impedance-sensitivity -- ground/supply-return impedance",
        "* sensitivity of design/sar_adc_top.spice (issue #378, DR-012's open item).",
        "* Assembled by sim/supply-impedance-sensitivity/run_supply_impedance.py;",
        "* the stimulus/measurement fragment is sim/full-conversion-transient's,",
        "* used verbatim except for the supply source cards' board-side nodes.",
        f"* arm={arm.name} corner={process_corner} temp={temp_c}C supply={supply_v}V",
        f".lib {pdk_info.ngspice_lib} {process_corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        f".include {stdcell_spice}",
        "* VPWR/VGND have no schematic-graph node inside sar_sequencer (see",
        "* design/sar_adc_top.sch's header); the testbench ties them here.",
        ".global VPWR VGND",
        "",
        dut_body,
        "",
        *decap_tie_comment_lines(arm, DECAP_TIE_RECORD),
        *decap_tie_cards,
        *([""] if decap_tie_cards else []),
        *arm_network_lines(arm),
        fragment,
        *extra_measure_lines(arm),
        ".end",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# A cost probe: what the box would cost, before the box is paid for
# --------------------------------------------------------------------------
# The two things #409 keeps failing on are the same thing: nobody knows what a
# deferred run costs until they have already spent it. The sweep's box is nine
# grid points plus the control -- ten whole-ADC transients, each tens of
# minutes -- and its expensive axis was assumed rather than measured: an
# undecoupled bond inductance forces the transient solver's timestep down, so
# "10x the inductance" reads like "10x the ringing", which reads like the row
# nobody can afford.
#
# A cost probe is the cheap answer: the SAME assembled deck, over a truncated
# transient. It measures nothing about the DUT -- the fragment's `.meas` cards
# sit at conversion times outside the sliced span, so the run reports no codes
# at all -- which is exactly why it is safe to run here and why it may never
# mint a record. What it does establish, per grid point, is (a) wall clock for a
# fixed simulated span, so the box's points can be priced relative to the one
# point that has a committed full-run measurement, and (b) that the point's deck
# assembles, parses and converges at all, which for every off-anchor point of
# the box is otherwise unknown until the hours have been spent.
RE_TRAN_CARD = re.compile(r"^\.tran\s+(\S+)\s+(\S+)[ \t]*$", re.MULTILINE)

#: SPICE engineering suffixes for a time value, as seconds.
_TIME_SUFFIX_S = {"": 1.0, "s": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


def _spice_time_ns(token: str) -> float | None:
    """`token` as nanoseconds, or None when it is not a plain SPICE time value.

    Deliberately conservative: an unrecognised form returns None and the caller
    skips the comparison it wanted, rather than this function guessing a
    magnitude and a probe silently being longer than the run it prices.
    """
    match = re.fullmatch(r"([0-9.]+(?:[eE][+-]?[0-9]+)?)\s*([a-zA-Z]*)", token.strip())
    if not match:
        return None
    suffix = match.group(2).lower()
    # ngspice accepts trailing unit noise ("6283n", "6283ns", "1ms"); the first
    # letter carries the scale, the rest is the unit name.
    scale = _TIME_SUFFIX_S.get(suffix) or _TIME_SUFFIX_S.get(suffix[:1] if suffix else "")
    if scale is None:
        return None
    return float(match.group(1)) * scale * 1e9


def truncate_tran(deck: str, slice_ns: float) -> str:
    """The same deck with its transient stop time cut to `slice_ns`.

    Only ever for `--cost-probe`. The timestep is left exactly as the committed
    fragment set it, because the solver work per simulated nanosecond is what a
    probe is measuring -- changing the requested step would change the thing
    being priced.
    """
    if slice_ns <= 0.0:
        raise RuntimeError("a cost probe's slice must be a positive number of nanoseconds")
    cards = RE_TRAN_CARD.findall(deck)
    if len(cards) != 1:
        raise RuntimeError(
            f"expected exactly one `.tran` card in the assembled deck, found {len(cards)} -- "
            "refusing to guess which one bounds the run"
        )
    step, stop = cards[0]
    stop_ns = _spice_time_ns(stop)
    if stop_ns is not None and slice_ns >= stop_ns:
        raise RuntimeError(
            f"a {slice_ns:g} ns cost probe is not shorter than the {stop_ns:g} ns run it "
            "exists to price -- run the campaign itself instead of probing it"
        )
    return RE_TRAN_CARD.sub(f".tran {step} {slice_ns:g}n", deck, count=1)


def fragment_tran_stop_ns() -> float | None:
    """The committed stimulus fragment's own transient stop time, in ns.

    Read from the fragment rather than restated here, so a probe's bound stays
    tied to the run it is pricing instead of to a constant that can drift from
    it. None when the card cannot be parsed, in which case callers skip the
    bound rather than inventing one.
    """
    cards = RE_TRAN_CARD.findall(tb.FRAGMENT_PATH.read_text())
    if len(cards) != 1:
        return None
    return _spice_time_ns(cards[0][1])


#: Log lines that mean the solver had trouble, not that a measurement failed.
#: A probe reports these per point: for every off-anchor point of the box, this
#: is the only evidence that the point is runnable at all before hours are
#: committed to it. `.meas` failures are NOT here on purpose -- a truncated run
#: is expected to miss every measurement, and treating that as trouble would
#: make the probe's one signal useless.
RE_SOLVER_TROUBLE = re.compile(
    r"(?i)(fatal|aborted|singular matrix|no convergence|timestep too small|"
    r"iteration limit reached)"
)


def solver_trouble_lines(log_text: str) -> list[str]:
    return [line.strip() for line in log_text.splitlines() if RE_SOLVER_TROUBLE.search(line)]


def run_cost_probe(
    arms: list[Arm], slice_ns: float, scratch: Path, quiet: bool
) -> list[dict]:
    """Wall clock for a truncated run of each arm's own deck, at the baseline
    corner, one simulation at a time. No measurement, no record."""
    pdk_info = pdk.resolve()
    dut_netlist_text = fc.dut_text()
    process_corner, temp_c, supply_v = BASELINE_CORNER
    rows: list[dict] = []
    for arm in arms:
        deck = truncate_tran(
            assemble_deck(dut_netlist_text, pdk_info, arm, process_corner, temp_c, supply_v),
            slice_ns,
        )
        t0 = time.time()
        log_text = toolchain.run_ngspice_with_retry(
            deck, scratch, f"cost_probe_{arm.name}", attempts=1
        )
        wall_s = time.time() - t0
        trouble = solver_trouble_lines(log_text)
        rows.append({"arm": arm.name, "wall_s": wall_s, "trouble": trouble})
        if not quiet:
            status = "converged" if not trouble else f"TROUBLE: {trouble[0]}"
            print(f"  {arm.name}: {wall_s:.1f}s over {slice_ns:g} ns ({status})", flush=True)
    return rows


def cost_probe_lines(rows: list[dict], slice_ns: float, anchor_arm: str) -> list[str]:
    """The probe's whole output: relative cost, and whether each point ran.

    Ratios against the anchor point, not absolute seconds, are what the caller
    can use: the anchor is the one point of the box that also has a committed
    full-run wall clock, so `full(point) ~ full(anchor) * ratio(point)` projects
    the box from a number this repo already recorded. Absolute seconds here are
    a contended shared host's, and are printed only to show the ratio's basis.
    """
    anchor = next((r for r in rows if r["arm"] == anchor_arm), None)
    out = [
        f"Cost probe over a {slice_ns:g} ns slice -- NOT A MEASUREMENT of this DUT:",
        "",
        "| point | wall clock (s) | x the anchor point | solver |",
        "|---|---|---|---|",
    ]
    for row in rows:
        ratio = (
            f"{row['wall_s'] / anchor['wall_s']:.2f}x"
            if anchor and anchor["wall_s"] > 0
            else "n/a"
        )
        solver = "converged" if not row["trouble"] else f"trouble: {row['trouble'][0]}"
        out.append(f"| `{row['arm']}` | {row['wall_s']:.1f} | {ratio} | {solver} |")
    if anchor is None:
        out += [
            "",
            f"This box does not contain the anchor point `{anchor_arm}`, so its "
            "numbers cannot be projected onto a committed full-run wall clock; they "
            "are relative to nothing but each other.",
        ]
    else:
        out += [
            "",
            f"The anchor point is `{anchor_arm}`. Multiply the ratio column by the "
            "committed full-run wall clock of the arm it is card-for-card identical "
            "to (`package`, in this campaign's arm-comparison record) to project what "
            "the full box would cost on this host.",
        ]
    troubled = [row["arm"] for row in rows if row["trouble"]]
    if troubled:
        out += [
            "",
            "The solver had trouble at: " + ", ".join(f"`{name}`" for name in troubled)
            + ". Those points are NOT known to be runnable over the full stimulus.",
        ]
    return out


# --------------------------------------------------------------------------
# A restartable log cache
# --------------------------------------------------------------------------
# One arm of this campaign is a whole-ADC transient that takes tens of minutes,
# and five of them in sequence outlive most process supervisors on a shared
# host. Losing four finished arms because the fifth was interrupted is a real
# and repeated cost, so a completed run's ngspice log can be cached and reused.
#
# The integrity rule: a cached log may be reused ONLY if it provably belongs to
# the same deck on the same toolchain. The sidecar therefore records the deck's
# own sha256, the *verified* open_pdks commit and the ngspice version, and any
# mismatch re-simulates rather than reusing. That makes the cache a restart
# mechanism, never a way for a stale number to reach a record: a record built
# from reused logs is byte-identical to one built by running them back to back,
# and it says which of its runs were reused.
#
# "Provably" is load-bearing, so an identity field this host cannot establish is
# not a field it may match on -- see _cache_identity() -- and the cache declines
# to store or reuse anything at all rather than gate on a placeholder that two
# different installs would both produce.


def _cache_key(point_id: str) -> str:
    return point_id.replace("@", "__")


def _cache_identity(deck: str, pdk_info: pdk.PdkInfo) -> dict | None:
    """The fields a cached log must match to be reusable, or None when this
    host cannot establish one of them.

    `pdk.resolved_commit_verified()`, deliberately, and NOT
    `pdk.resolved_commit()`: the latter is a *display* string whose own
    docstring forbids treating it as proof of the install's provenance,
    because for any non-volare install it falls back to the expected pin
    annotated "(unverified -- no SOURCES file or volare layout)". `toolchain.check_env()`
    treats a non-volare install as a warning rather than a failure, so that
    fallback is reachable in a real run -- and it is a *constant*: two
    genuinely different hand-installed model libraries produce the identical
    string, so gating on it would let the cache hand back a log simulated
    against library A for a run against library B. That is exactly the stale
    number this gate exists to keep out of an append-only record.

    The ngspice version gets the same treatment: "unknown" == "unknown" is not
    a match, it is two hosts that both failed to answer. When either value is
    unknowable there is no identity to gate on, so callers refuse rather than
    matching on a placeholder.
    """
    open_pdks_commit = pdk.resolved_commit_verified(pdk_info)
    ngspice_version = toolchain._ngspice_version()
    if open_pdks_commit is None or ngspice_version is None:
        return None
    return {
        "deck_sha256": evidence.sha256_text(deck),
        "open_pdks_commit": open_pdks_commit,
        "pdk_variant": pdk_info.variant,
        "ngspice": ngspice_version,
    }


def load_cached_run(
    log_cache: Path | None, point_id: str, deck: str, pdk_info: pdk.PdkInfo
) -> tuple[str, float] | None:
    """`(log_text, wall_s)` for a cached run of exactly this deck, else None."""
    if log_cache is None:
        return None
    key = _cache_key(point_id)
    log_path = log_cache / f"{key}.log"
    meta_path = log_cache / f"{key}.json"
    if not (log_path.is_file() and meta_path.is_file()):
        return None
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    want = _cache_identity(deck, pdk_info)
    if want is None:
        print(
            f"  cached log for {point_id} ignored: this host cannot verify the "
            "open_pdks commit or the ngspice version, so no stored log is provably "
            "this deck's on this toolchain -- re-simulating",
            flush=True,
        )
        return None
    for field, value in want.items():
        if meta.get(field) != value:
            print(
                f"  cached log for {point_id} ignored: {field} differs "
                f"({meta.get(field)!r} cached vs {value!r} now) -- re-simulating",
                flush=True,
            )
            return None
    # A sidecar with no usable wall_s is malformed, not a run that took 0 s:
    # reporting 0 would land in the record's wall-clock table as `0` and
    # `0.00x`. Same disposition as every other unreadable field -- re-simulate.
    try:
        wall_s = float(meta["wall_s"])
    except (KeyError, TypeError, ValueError):
        print(
            f"  cached log for {point_id} ignored: sidecar has no usable wall_s "
            f"({meta.get('wall_s')!r}) -- re-simulating",
            flush=True,
        )
        return None
    return log_path.read_text(), wall_s


def store_cached_run(
    log_cache: Path | None,
    point_id: str,
    deck: str,
    pdk_info: pdk.PdkInfo,
    log_text: str,
    wall_s: float,
) -> None:
    if log_cache is None:
        return
    meta = _cache_identity(deck, pdk_info)
    if meta is None:
        # Nothing to write a gate against: a log stored without a verifiable
        # identity could only ever be reused by weakening the gate later.
        print(
            f"  not caching {point_id}: this host cannot verify the open_pdks "
            "commit or the ngspice version, so the log has no provable identity",
            flush=True,
        )
        return
    log_cache.mkdir(parents=True, exist_ok=True)
    key = _cache_key(point_id)
    (log_cache / f"{key}.log").write_text(log_text)
    meta["wall_s"] = wall_s
    meta["point_id"] = point_id
    (log_cache / f"{key}.json").write_text(json.dumps(meta, indent=2) + "\n")


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------
def run_point(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    arm: Arm,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    log_cache: Path | None = None,
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    deck = assemble_deck(dut_netlist_text, pdk_info, arm, process_corner, temp_c, supply_v)
    point_id = f"{arm.name}@{cid}"

    cached = load_cached_run(log_cache, point_id, deck, pdk_info)
    if cached is not None:
        log_text, wall_s, reused = cached[0], cached[1], True
        print(f"  reusing cached log for {point_id} ({wall_s:.0f}s when it ran)", flush=True)
    else:
        t0 = time.time()
        log_text = toolchain.run_ngspice_with_retry(
            deck, scratch, f"supply_impedance_{arm.name}_{cid}", attempts=3
        )
        wall_s = time.time() - t0
        reused = False
        store_cached_run(log_cache, point_id, deck, pdk_info, log_text, wall_s)

    names = tb.all_measure_names() + extra_measure_names(arm)
    parsed = measure.parse(log_text, names, anchored=False)
    missing = measure.missing(parsed, names)
    result = fc.decode(parsed, supply_v)
    result.update(
        arm=arm.name,
        process_corner=process_corner,
        temp_c=temp_c,
        supply_v=supply_v,
        corner_id=cid,
        point_id=point_id,
        extras={name: parsed.get(name) for name in extra_measure_names(arm)},
        missing=missing,
        log_text=log_text,
        deck_text=deck,
        wall_s=wall_s,
        reused=reused,
    )
    if missing:
        result["all_ok"] = False
    return result


def mid_scale_conversions(point: dict) -> list[dict]:
    """The conversions whose captured code this campaign reads an arm-to-arm
    delta from. The two near-full-scale inputs (`+-0.78*V_REF`) are excluded
    from the delta on purpose: `sim/full-conversion-transient/records/`
    already records them as broken by ~100 LSB at every corner (issue #267,
    common-mode saturation at large differential input, still open), so a
    change there cannot be attributed to supply impedance. They are still
    reported in full below -- excluded from the comparison, not from the
    record.
    """
    return [cv for cv in point["conversions"] if abs(cv["fraction"]) <= 0.5]


def code_delta(point: dict, control: dict) -> dict:
    """Per-conversion captured-code difference against the control arm."""
    by_conv = {cv["conversion"]: cv for cv in control["conversions"]}
    deltas: dict[int, int | None] = {}
    for cv in point["conversions"]:
        ref = by_conv.get(cv["conversion"])
        if ref is None or cv["code"] is None or ref["code"] is None:
            deltas[cv["conversion"]] = None
        else:
            deltas[cv["conversion"]] = cv["code"] - ref["code"]
    return deltas


def worst_mid_scale_delta(point: dict, control: dict) -> int | None:
    deltas = code_delta(point, control)
    values = [
        abs(deltas[cv["conversion"]])
        for cv in mid_scale_conversions(point)
        if deltas.get(cv["conversion"]) is not None
    ]
    return max(values) if values else None


def format_point(point: dict) -> str:
    codes = " ".join(
        f"{cv['fraction']:+.2f}:{'?' if cv['code'] is None else cv['code']}"
        for cv in point["conversions"]
    )
    gnd_pp = point["extras"].get("gnd_die_pp")
    gnd_str = "n/a" if gnd_pp is None else f"{gnd_pp * 1e3:.3f} mV"
    return (
        f"{point['point_id']}: codes {codes} "
        f"GND_die pp={gnd_str} ({point['wall_s']:.0f}s)"
    )


def full_ratified_grid() -> list[tuple[str, float, float]]:
    """The nine ratified OAT points, in `ratified_oat_grid()`'s own order."""
    return corners_mod.ratified_oat_grid(
        NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
    )


def resolve_grid(corners_mode: bool, corner_points: list[str]) -> list[tuple[str, float, float]]:
    """Which points of the ratified grid this invocation runs.

    Three shapes, one of which is new (issue #409 item 1): the baseline corner
    (default), the whole ratified grid (`--corners`), or a NAMED SUBSET of that
    same grid (`--corner-points`). The subset exists because the grid is hours
    of sequential whole-ADC transients and a dispatch host's session is not --
    `.loom/docs/long-running-compute.md` allows local simulation but forbids a
    process outliving the session that started it, so the sanctioned way to
    reach nine points is to run the ones a session can afford and let
    `--log-cache` carry the finished ones forward. A subset is never a new
    corner: the ids are looked up IN the ratified grid, so this flag can narrow
    the ratified set but can never invent a point outside it.
    """
    grid = full_ratified_grid()
    if corner_points:
        by_id = {corners_mod.corner_id(*point): point for point in grid}
        unknown = [cid for cid in corner_points if cid not in by_id]
        if unknown:
            raise ValueError(
                f"corner point(s) {unknown} are not in the ratified grid -- "
                f"available: {sorted(by_id)}"
            )
        # Ratified-grid order, not the order the caller happened to type.
        return [point for cid, point in by_id.items() if cid in set(corner_points)]
    if corners_mode:
        return grid
    return [BASELINE_CORNER]


def run_campaign(
    arms: list[Arm],
    grid: list[tuple[str, float, float]],
    quiet: bool,
    scratch: Path,
    log_cache: Path | None = None,
) -> tuple[list[dict], str]:
    """Run each arm at each corner point, one simulation at a time.

    Takes `Arm` objects rather than names because `--sweep` synthesizes its
    grid points (`sweep_arm()`) instead of choosing from `ARMS`; both modes
    otherwise run through exactly the same deck assembly, cache and
    measurement path, so a sweep point is the same kind of evidence as an arm.
    """
    pdk_info = pdk.resolve()
    dut_netlist_text = fc.dut_text()

    points: list[dict] = []
    for arm in arms:
        for process_corner, temp_c, supply_v in grid:
            point = run_point(
                dut_netlist_text,
                pdk_info,
                scratch,
                arm,
                process_corner,
                temp_c,
                supply_v,
                log_cache=log_cache,
            )
            points.append(point)
            if not quiet:
                print("  " + format_point(point), flush=True)
    return points, dut_netlist_text


# --------------------------------------------------------------------------
# Evidence record: the rendering helpers every campaign's writer shares
# --------------------------------------------------------------------------
# Each campaign's own `write_*_record` lives in that campaign's module; what
# sits here is the part two or more of them call -- the unit formatters, the
# arm/assumption/provenance blocks, and the corner-subset and per-run tables
# that read identically whichever campaign minted the record.
def _mv(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e3:.3f}"


def _ua(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e6:.3f}"


def _uw(power_w: float | None) -> str:
    """Total power in uW, or `n/a` when `fc.decode()` marked it unavailable
    (a missing or non-finite supply current at a nonzero potential, #569/#573)
    -- the same convention as `run_conversion.format_point()`/`write_record()`.
    An unavailable power is never rendered as a partial sum or as zero."""
    return "n/a" if power_w is None else f"{power_w * 1e6:.3f}"


def _avg_current_cells(p: dict) -> str:
    """The `I(VDD) | I(VPWR) | I(GND) | I(VREFP) | I(VCM) | total power` cells
    of an average-rail-current row, shared by `write_record()` and
    `write_decap_esr_record()`. Every value may be unavailable and renders as
    `n/a`; `I(GND)` reads `n/a (no bond)` where the arm has no ground bond."""
    i_gnda = p["extras"].get("i_gnda")
    return (
        f"{_ua(p['currents'].get('i_vdd'))} | "
        f"{_ua(p['currents'].get('i_vpwr'))} | "
        f"{'n/a (no bond)' if i_gnda is None else _ua(abs(i_gnda))} | "
        f"{_ua(p['currents'].get('i_vrefp'))} | "
        f"{_ua(p['currents'].get('i_vcm'))} | "
        f"{_uw(p['power_w'])} |"
    )


def _assumption_lines() -> list[str]:
    return [
        "| element | value | where it comes from |",
        "|---|---|---|",
        (
            f"| bond-wire inductance | {BOND_L_H * 1e9:.3f} nH | "
            f"straight round-wire self-inductance `L = (mu0*l/2pi)(ln(2l/r) - 3/4)` "
            f"for l = {BOND_WIRE_LENGTH_MM:g} mm, d = {BOND_WIRE_DIAMETER_UM:g} um "
            "(computed in `run_supply_impedance.py`, not quoted from anywhere) |"
        ),
        (
            f"| bond-wire resistance | {BOND_R_OHM * 1e3:.1f} mOhm | "
            f"`rho*l/A` for the same wire, gold `rho = {GOLD_RESISTIVITY_OHM_M:.2e}` Ohm*m |"
        ),
        (
            f"| lead-frame + board allowance | {LEAD_FRAME_L_NH:g} nH, "
            f"{LEAD_FRAME_R_MOHM:g} mOhm | a STATED allowance for the path between "
            "the package pin and the board star point -- an assumption, not a "
            "derivation (DR-015) |"
        ),
        (
            f"| **per-terminal total** | **{PACKAGE_R_OHM * 1e3:.1f} mOhm + "
            f"{PACKAGE_L_H * 1e9:.3f} nH** | the `package` / `no-gnd-pad` arms' "
            "series impedance on each bonded terminal |"
        ),
        (
            f"| substrate stand-in `R_SUB` | {R_SUB_OHM:g} Ohm | a LUMPED stand-in, "
            "magnitude from DR-012's own \"10s of ohms of p-substrate\" wording. "
            "NOT an extracted substrate network -- see the caveat below |"
        ),
        (
            f"| substrate link `R_SUBX` | {R_SUBX_OHM:g} Ohm | lumped stand-in for the "
            "path that makes `GND` and `VGND` one extracted net (DR-012); present "
            "in every arm, carrying no current in `ideal` |"
        ),
    ]


def _ohms(r_ohm: float) -> str:
    """Resistances here span three decades (a bond wire vs a substrate
    stand-in), so the unit follows the value rather than forcing `30000 mOhm`."""
    return f"{r_ohm:g} Ohm" if r_ohm >= 1.0 else f"{r_ohm * 1e3:.1f} mOhm"


def _bond_cell(arm: Arm, terminal: str) -> str:
    """One arm's series network on one supply terminal, as the record states it."""
    if terminal not in arm.bonds:
        return "**no bond** (substrate only)"
    bond = arm.bonds[terminal]
    if bond is None:
        return "ideal source at the die"
    if bond.l_h <= 0.0:
        return f"R = {_ohms(bond.r_ohm)}"
    return f"R = {_ohms(bond.r_ohm)} + L = {bond.l_h * 1e9:.3f} nH"


def arm_table_lines(arms: list[Arm], substrate_note: bool = True) -> list[str]:
    """One row per arm, as networks.

    Takes `Arm` objects rather than names so the sweep's synthesized grid
    points (`sweep_arm()`), which are not in `ARMS`, render through the same
    table as the named arms.
    """
    out = [
        "| arm | " + " | ".join(f"`{t}`" for t in TERMINAL_ORDER) + " | what it isolates |",
        "|---" * (len(TERMINAL_ORDER) + 2) + "|",
    ]
    for arm in arms:
        cells = " | ".join(_bond_cell(arm, t) for t in TERMINAL_ORDER)
        out.append(f"| `{arm.name}` | {cells} | {arm.summary} |")
    out.append("")
    if substrate_note:
        out.append(
            f"Every arm also carries one lumped `R_SUBX = {R_SUBX_OHM:g} Ohm` between "
            "the analog and digital ground DIE nodes, because DR-012's own extraction "
            "evidence says those two are one net through the p-substrate. In "
            f"`{CONTROL_ARM}` both of its ends are held at 0 V by ideal sources, so it "
            "carries no current and the control stays a true zero-impedance reference."
        )
    return out


def _stimulus_bullet() -> str:
    """The `Stimulus` header bullet shared by all four record writers."""
    return (
        "- **Stimulus**: `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice`, unmodified except for the supply "
        f"source cards' nodes -- `f_clk = {tb.F_CLK_HZ / 1e6:g} MHz` (DR-006 worst "
        f"case), {tb.N_CONVERSIONS} back-to-back conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods, the first discarded as start-up, "
        "the remaining five carrying DC differential inputs of "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + "."
    )


def _provenance_bullet(rewire_scope: str = "") -> str:
    """The two-transformation `Netlist provenance` header bullet.

    `rewire_scope` is an optional phrase (leading space included) that narrows
    where the source cards are re-pointed; `write_record()` passes one because
    only some of its arms bond the supplies through an impedance. The
    three-transformation decap-ESR text and the midscale-probe text make
    different claims and stay inline in their writers.
    """
    return (
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with two "
        "TESTBENCH-ONLY transformations that are never written back to `design/`: "
        "the DUT's `GND` net is renamed `GND_DIE` (a net named `GND` is ngspice's "
        "global node 0 and would short out every series element this campaign "
        "inserts), and the committed fragment's `VVDD`/`VVPWR`/`VVGND` source "
        f"cards are re-pointed to board-side nodes{rewire_scope}. Source instance "
        "names, the `.tran` card, the clock/reset/input schedule and every code and "
        "phase `.meas` card are used verbatim."
    )


def _open_corners_record(
    points: list[dict], dut_netlist_text: str
) -> tuple[evidence.ProvenanceInfo, list[str], list[str], list[str], list[float], list[float]]:
    """Open a `corners` record, dump each point's raw log and deck, and derive
    the corner/process/temperature/supply summaries every one of the four
    writers below needs before its own arm/control derivation.

    Deliberately stops there (issue #486). `write_record()` goes on to compute
    `arms_run` (the ARM NAMES touched by any point) and `controls` (one
    CONTROL PER CORNER, keyed by corner id) because it supports a multi-corner
    `corners` run with its own control at each point; the other three writers
    instead compute a single point-filter list (`grid_points`/`swept`/`rungs`)
    and one `control` point, because each of them runs at a single corner.
    That is a real difference in what each writer needs, not a copy-pasted
    variable name, so each writer keeps computing its own version rather than
    this helper trying to parameterize it away.
    """
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR,
        dut_netlist_text,
        "corners",
        {f"{p['point_id'].replace('@', '__')}.log": p["log_text"] for p in points},
    )
    deck_dir = EXPERIMENT_DIR / "corners" / prov.record_id
    for p in points:
        (deck_dir / f"{p['point_id'].replace('@', '__')}.cir").write_text(p["deck_text"])
    corner_ids = sorted({p["corner_id"] for p in points})
    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})
    return prov, lines, corner_ids, processes, temps, supplies


def subset_corner_lines(
    corner_ids: list[str],
    what_ran: str,
    decks_label: str,
    n_decks: int,
    what_it_is_instead: str,
) -> list[str]:
    """`sim/README.md`'s required justification for running a subset of the
    ratified corner set, shared by every record this runner writes.

    It is one argument, not one per record mode: the constraints below are
    properties of the HOST and of the cost of one whole-ADC transient, so a
    second record mode that also runs a corner subset must state the same ones
    and must not get to paraphrase them into something weaker. Only the
    sentence naming what ran, and the cost arithmetic, differ.

    The constraint set was RE-DERIVED against a measuring host on 2026-09-25
    (issue #409 item 1) rather than carried forward: the earlier wording said
    this host's operating rules forbade a local multi-corner grid at all, and
    that is not what binds. A dispatch host may run ngspice locally -- every
    run in the table above did -- but no process of a session may outlive it
    (`.loom/docs/long-running-compute.md`), so what binds is that the whole
    grid must fit inside one session or be advanced in pieces across several.
    The obsolete reason is not merely replaced, it is named, because a record
    that quietly swapped its justification would be indistinguishable from one
    that never checked.
    """
    baseline_id = corners_mod.corner_id(*BASELINE_CORNER)
    partial_grid = corner_ids != [baseline_id]
    out = [
        "## Subset-corner justification (`sim/README.md`)",
        "",
        (
            f"This record runs {what_ran} at {len(corner_ids)} point(s) of the "
            f"ratified corner set ({', '.join('`' + c + '`' for c in corner_ids)}), "
            "not all nine. Two constraints bind, and neither of them is a "
            "judgement that the corners do not matter:"
        ),
        "",
        (
            f"- **Cost, against a session that must end.** The nine-point ratified "
            f"grid across {decks_label} is {9 * n_decks} whole-ADC transients at "
            "the per-run wall clock measured above -- hours, and the arithmetic is "
            "in the table rather than in a projection. The host is a dispatch "
            "worker on which an agent session may run ngspice locally (every run "
            "above did) but on which **no process may outlive the session that "
            "started it** (`.loom/docs/long-running-compute.md`); the sanctioned "
            "answer there is to scope the run to the session and land the "
            "increment, which is what this record is. `--corner-points` runs a "
            "named subset of the same ratified grid and `--log-cache` carries "
            "finished points across sessions, so the grid is completed by "
            "accumulation -- each session adding the points it can afford -- "
            "rather than needing one sitting long enough to hold all of it."
        ),
        (
            "- **The batch route cannot mint a record in THIS repo's format.** "
            "`klt sim` owns its own request/response JSON contract and its own "
            "corner expansion; every record under `sim/` is written by this repo's "
            "`sim/harness/evidence.py` against a deck this repo assembles. Routing "
            "the grid through `klt sim` would produce a different artefact, not "
            "this one. Separately, the fleet's runner image installs ngspice from "
            "the distribution archive, and this repo's own CI already records what "
            "that means: `.github/workflows/ci.yml` states that the archive build "
            "is **ngspice-42**, below `sim/toolchain.json`'s "
            "`ngspice_min_major = 46` floor, which is why CI builds ngspice from "
            "source instead. A record minted below that floor is refused by "
            "`sim/check_spec_coverage.py`'s pin gate and would not be comparable "
            "with anything already under `sim/`."
        ),
        (
            "- **What is NOT a constraint, and used to be stated as one.** The "
            "host's ngspice satisfies `sim/toolchain.json`'s floor (the "
            "environment block below names the exact build), and local "
            "multi-corner simulation is not forbidden here -- the points above "
            "were run locally, one at a time, in a single session. Records before "
            "issue #409 item 1 stated a blanket host-policy ban; that reason was "
            "re-checked on a measuring host and retired."
        ),
        "",
        (
            "So the ratified-grid run is **partially done and still open**, not "
            "skipped: the runner implements the whole of it (`--corners`, the "
            "nine-point `ratified_oat_grid()` x the decks), this experiment's "
            "README names the exact command, and "
            + (
                f"{len(corner_ids)} of the nine points are now measured here. "
                "The remaining points are owed and are tracked in issue #409."
                if partial_grid
                else "what is owed is the eight non-baseline points, tracked in "
                "issue #409."
            )
            + " Until they are in a record, no statement here is a "
            f"corner-worst-case claim; it is {what_it_is_instead}."
        ),
        "",
    ]
    return out


def _captured_code_table_lines(
    points: list[dict], control: dict | None, row_label: str
) -> list[str]:
    """The "Captured code per point/rung" table, shared verbatim (modulo the
    row label) across `write_sweep_record`, `write_null_sweep_record`, and
    `write_decap_esr_record` -- `write_record()` has no equivalent block, it
    reports captured codes per corner-id x arm instead."""
    out = [
        f"| {row_label} | "
        + " | ".join(f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)})" for f in tb.INPUT_FRACTIONS)
        + " | worst \\|delta code\\| vs `ideal` (mid-scale) |",
        "|---" * (len(tb.INPUT_FRACTIONS) + 2) + "|",
    ]
    for p in points:
        deltas = code_delta(p, control) if control else {}
        cells = []
        for cv in p["conversions"]:
            code = "MISSING" if cv["code"] is None else str(cv["code"])
            delta = deltas.get(cv["conversion"])
            suffix = "" if delta is None or p["arm"] == CONTROL_ARM else f" ({delta:+d})"
            cells.append(f"{code}{suffix}")
        worst = (
            "-- (control)"
            if p["arm"] == CONTROL_ARM
            else worst_mid_scale_delta(p, control) if control else "n/a"
        )
        out.append(f"| `{p['arm']}` | " + " | ".join(cells) + f" | {worst} |")
    return out


def _rail_current_table_lines(
    points: list[dict], row_label: str, extra_note: str | None = None
) -> list[str]:
    """The "Rail excursion and average current per point" table, shared
    verbatim across the two writers that have it -- `write_sweep_record` and
    `write_null_sweep_record`. `write_record()` and `write_decap_esr_record()`
    each report rail excursion and average current as separate tables and have
    no equivalent single block. `extra_note`, if given, is appended as its own
    paragraph after the table -- `write_null_sweep_record()`'s one-sentence
    addition that `I(GND)` is `n/a (no bond)` on every swept row by
    construction."""
    out = [
        f"| {row_label} | "
        + " | ".join(f"{name} pp (mV)" for name, _n, _l in RAIL_PROBES)
        + " | I(VDD) (uA) | I(VPWR) (uA) | I(GND) (uA) | total power (uW) |",
        "|---" * (len(RAIL_PROBES) + 5) + "|",
    ]
    for p in points:
        cells = [_mv(p["extras"].get(f"{probe}_pp")) for probe, _n, _l in RAIL_PROBES]
        i_gnda = p["extras"].get("i_gnda")
        out.append(
            f"| `{p['arm']}` | "
            + " | ".join(cells)
            + f" | {_ua(p['currents'].get('i_vdd'))} | {_ua(p['currents'].get('i_vpwr'))} | "
            + f"{'n/a (no bond)' if i_gnda is None else _ua(abs(i_gnda))} | "
            + f"{_uw(p['power_w'])} |"
        )
    out.append("")
    if extra_note:
        out.append(extra_note)
        out.append("")
    return out


def _wall_clock_table_lines(
    points: list[dict], control: dict | None, row_label: str
) -> list[str]:
    """The "Wall-clock cost per run" table and its cache-reuse note, shared
    across `write_sweep_record`, `write_null_sweep_record`, and
    `write_decap_esr_record` -- `write_record()` has no equivalent block, its
    own wall-clock table is keyed by corner-id x arm instead. Each writer
    appends its own trailing sentence about why the cost is reported after
    calling this; that sentence is writer-specific and is not part of this
    helper.

    The cache-reuse note is the FULL four-sentence version -- the two sweep
    writers' own copies before this helper existed, not
    `write_decap_esr_record()`'s shorter one, which had silently dropped the
    "a mismatch on any identity field re-simulates" and "a host that cannot
    verify ..." sentences (issue #486). Reconciled to the fuller text so all
    three writers state the same cache-reuse guarantee.
    """
    out = [
        f"| {row_label} | wall clock (s) | x the `ideal` control |",
        "|---|---|---|",
    ]
    base = None if control is None else control.get("wall_s")
    for p in points:
        ratio = "--" if not base else f"{p['wall_s'] / base:.2f}x"
        note = " (log reused from cache)" if p.get("reused") else ""
        out.append(f"| `{p['arm']}` | {p['wall_s']:.0f}{note} | {ratio} |")
    out.append("")
    if any(p.get("reused") for p in points):
        out.append(
            "Rows marked **log reused from cache** were not re-simulated for this "
            "record: `--log-cache` found a stored ngspice log whose deck sha256, "
            "volare-verified open_pdks commit and ngspice version all matched the "
            "run about to be made, and reused it rather than repeating a "
            "tens-of-minutes transient after an interruption. The reported wall "
            "clock is the one measured when that run actually executed. A mismatch "
            "on any identity field re-simulates, and a host that cannot verify its "
            "own open_pdks commit or ngspice version never reuses at all."
        )
        out.append("")
    return out


# --------------------------------------------------------------------------
# One LSB, in volts
# --------------------------------------------------------------------------
# Defined with the mid-scale probe (which reads codes in LSB), but read by
# the `--sweep` and `--null-sweep` findings too, so it is shared rather than
# a campaign's own.
def lsb_v(supply_v: float) -> float:
    """One differential LSB: `2*V_REF/2^N` with `V_REF = V_DD` (DR-003)."""
    return 2.0 * supply_v / (2**tb.N_BITS)

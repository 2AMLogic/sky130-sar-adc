#!/usr/bin/env python3
"""Ground/supply-return impedance sensitivity of the assembled ADC (issue
#378, DR-012's own open item).

    source sim/env.sh
    python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --check-env
    python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --record
    python3 sim/supply-impedance-sensitivity/run_supply_impedance.py --corners --record

WHAT THIS IS. `spec/decision-records/DR-012-analog-ground-pad.md` decided
that this block presents a **drawn** analog `GND` pad rather than bonding
its analog ground through the substrate only. That record says, in its own
words, that its reasoning is a design-time argument and that "no `sim/`
campaign in this repo models the ground return at all -- no package
parasitics, no substrate resistance, no bond-wire inductance". This campaign
is the testbench that record names: it runs
`sim/full-conversion-transient/`'s own stimulus, unmodified, against the
same committed `design/sar_adc_top.spice`, with the four supply terminals
(`VDD`, `GND`, `VPWR`, `VGND`) driven through package-like R+L instead of
ideal sources, and compares the captured codes and the die-side ground
excursion against the ideal-source case.

THE FIVE ARMS (see `ARMS` below for the exact networks):

  `ideal`           every supply terminal driven by an ideal source AT the
                    die node. This is what every existing campaign in `sim/`
                    runs today -- including, for `GND`, by accident rather
                    than by choice: ngspice aliases a node literally named
                    `gnd` onto node `0`, so the committed fragment's
                    *absence* of a `GND` source is exactly a zero-impedance
                    ground. The control.
  `package-r-only`  all four terminals bonded through the package R, with
                    L = 0. Paired with `package` below this is a strict
                    one-element ablation: the ONLY difference between the two
                    is the bond inductance, so `package` minus this arm is
                    that inductance's own contribution and nothing else.
  `package`         all four terminals bonded through R+L (DR-012's as-built
                    shape: four drawn pads, star point off-die).
  `substrate`       no bond inductance anywhere; a lumped resistance of the
                    SUBSTRATE's own order (`R_SUB`, tens of ohms) in the two
                    ground returns only. This is the on-die/substrate
                    resistive-return magnitude, NOT an ablation of `package`
                    -- its resistance is ~300x the package R, so it answers
                    "what would an on-die-only return cost?" and the
                    `package-r-only` arm above answers "what does the bond's
                    own resistance cost?".
  `no-gnd-pad`      DR-012's REJECTED null option, measured: `GND` gets no
                    bond of its own and reaches the board only through the
                    lumped substrate resistance to `VGND`'s die node and out
                    through *its* bond. The other three terminals keep their
                    R+L. Paired with `package` this is the campaign's SECOND
                    strict one-element ablation -- same three bonded
                    terminals, same substrate link, the only difference is
                    whether `GND` is bonded -- so that pair prices the option
                    DR-012 rejected against the option it chose. It was long
                    believed to be the most expensive arm by a wide margin, on
                    a truncated-slice projection; the full run measured 1.67x
                    the control, CHEAPER than `package`. See this experiment's
                    README on runtime for why the projection was wrong, and
                    `--null-sweep` below for the sweep that projection blocked.

WHAT THE SUBSTRATE RESISTOR IS NOT. There is no extracted substrate network
in this repo. `R_SUB`/`R_SUBX` below are a **lumped stand-in** whose
magnitude is taken from DR-012's own wording ("10s of ohms of p-substrate
between the comparator's taps and a paddle contact"), not from an
extraction, and no result here may be quoted as a measured substrate
resistance. The R+L values are likewise a *stated package-style assumption*
derived from textbook wire geometry in `PACKAGE_*` below and ratified as an
assumption by `spec/decision-records/DR-015-package-parasitic-assumption.md`
-- not a measurement of any package.

DECK ASSEMBLY (two testbench-only transformations, neither written back to
`design/`, both asserted so a netlist/fragment shape change fails loudly):

  1. The DUT's `GND` net is renamed to `GND_DIE`. This is not cosmetic and
     it is not optional: ngspice aliases the node name `gnd` onto the global
     ground node `0`, so a series impedance on a net still named `GND` would
     be silently shorted out and the whole campaign would measure nothing.
  2. The committed fragment's own `VVDD`/`VVPWR`/`VVGND` source cards are
     re-pointed from the die node to a board-side node when that terminal is
     bonded through R+L. The source INSTANCE names are unchanged, so the
     fragment's own `.meas ... avg i(vvdd)` cards keep measuring the same
     thing (the current delivered from the board), and the `.tran` card,
     every code/phase `.meas`, the clock, the reset and the input schedule
     are used verbatim. `VREFP`/`VREFN`/`VCM` stay ideal at the die: this
     campaign is about the four *supply* terminals DR-012 names, and a
     reference-network campaign is a different experiment.

The clock, reset and input sources stay referenced to node `0` (the
board-side star point), which is the physically honest choice for off-die
stimulus and is what makes a die-side ground excursion appear where it
really appears: as a shift between the die's own reference and everything
the outside world drives.

THE BOUNDED 2-D SWEEP (`--sweep`, issue #409's third item). The five arms
above all sit at ONE point of DR-015's assumed magnitudes, which can only
show whether the mechanism matters at that point -- never the magnitude at
which it starts to matter. `--sweep` is DR-015's own named follow-up: the
as-built `package` topology, re-run over a bounded grid of per-terminal bond
inductance x lumped substrate-link resistance at the baseline corner, plus
the same `ideal` control. See `SWEEP_*` below for the box and for why the
substrate axis is `R_SUBX` rather than `R_SUB`.

THE BOUNDED NULL-OPTION SUBSTRATE LADDER (`--null-sweep`, issue #409). The
2-D box above moves a substrate resistance on the AS-BUILT network, where
`GND` is bonded and that resistor is a secondary shunt. `--null-sweep` moves
the same constant where it is load-bearing instead: on the `no-gnd-pad`
topology, whose analog ground reaches the board only through it. That is the
measured version of DR-015's own prose claim that the rejected option is
"entirely a function of `R_SUB`: with a small `R_SUB` it looks harmless, with
a large one it looks fatal" -- a claim made, until that ladder ran, from one
point. See `NULL_SWEEP_*` below.

PRICING A BOX BEFORE PAYING FOR IT (`--cost-probe NS`). The 2-D box is ten
whole-ADC transients, so the first question about it is what it costs and
whether its off-anchor points converge at all -- neither of which is knowable
from the arm-comparison record, which contains one of the ten. `--cost-probe`
re-runs each grid point's own deck over a TRUNCATED transient and reports only
wall clock and solver status. It measures nothing about the DUT (the
fragment's `.meas` cards sit outside the sliced span) and is refused with
`--record`, so it cannot become evidence about this block -- only about what
running the box would cost.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
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
#: The DUT's analog-ground net, renamed at deck-assembly time (see the module
#: docstring): a net named `GND` is ngspice's global node 0 and cannot carry
#: a series impedance.
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


# --------------------------------------------------------------------------
# The bounded 2-D R/L sweep (issue #409 item 3; DR-015's own open item)
# --------------------------------------------------------------------------
# The five arms above are five NETWORKS at ONE point of DR-015's assumed
# magnitudes. That shows whether the mechanism matters at that point; it
# cannot show the magnitude at which it starts to. DR-015 says so itself, in
# both its "Alternatives considered" ("Sweep R/L over a range instead of
# fixing one point ... this is the better experiment") and its "Open items"
# ("A bounded 2-D sweep (bond inductance x substrate resistance) at one
# corner is the natural follow-up").
#
# WHAT IS SWEPT. The deck is the AS-BUILT `package` arm -- all four supply
# terminals bonded, DR-012's chosen shape -- with two axes:
#
#   * `SWEEP_L_MULTIPLIERS`: the per-terminal bond INDUCTANCE, as a multiple
#     of DR-015's own value. `0x` is an inductance-free bond (electrically the
#     `package-r-only` arm), `1x` is DR-015's assumption point (electrically
#     the `package` arm), and the top of the ladder is a deliberately bad bond
#     -- a long wire, or a return with no nearby ground plane.
#   * `SWEEP_RSUBX_OHM`: the lumped substrate link between the analog and
#     digital ground DIE nodes, a decade either side of DR-015's 30 Ohm. This
#     is "how hard the p-substrate ties the two ground domains together" --
#     DR-012's own premise that `GND` and `VGND` are one extracted net -- and
#     it is what decides how much of the digital ground's switching current
#     returns through the analog bond.
#
# So a ROW of the grid (one `R_SUBX`, the L ladder) changes exactly one
# element, and so does a COLUMN. That is DR-015 item 5's requirement -- an
# effect may be attributed to an element only by a difference that moves that
# element and nothing else -- satisfied by construction for both axes.
#
# WHY THIS AXIS IS A SHUNT, NOT A RETURN. On the as-built deck `GND` has a
# bond of its own, so the resistor this axis moves sits BESIDE that bond as a
# shunt between the two ground die nodes -- it decides how much of the digital
# ground's switching current comes back through the analog bond, not how the
# analog ground reaches the board. The topology where that same resistor IS
# the whole analog-ground return is `no-gnd-pad`, and sweeping it there is a
# different experiment with a different reading: `--null-sweep` below. Every
# record this sweep writes says which of the two it moved rather than letting
# "substrate resistance" be read as both.
SWEEP_BASE_ARM = "package"

#: Multipliers of DR-015's per-terminal bond inductance `PACKAGE_L_H`.
SWEEP_L_MULTIPLIERS: tuple[float, ...] = (0.0, 1.0, 10.0)

#: The lumped substrate link `R_SUBX`, in ohms: a decade either side of
#: DR-015's assumed 30 Ohm.
SWEEP_RSUBX_OHM: tuple[float, ...] = (3.0, 30.0, 300.0)


def sweep_arm_name(l_mult: float, rsubx_ohm: float) -> str:
    """The grid point's arm name -- also its log/deck filename and its cache
    key, so it carries both coordinates and no separator that a path would
    choke on."""
    return f"sweep-l{l_mult:g}x-rsubx{rsubx_ohm:g}"


def sweep_arm(l_mult: float, rsubx_ohm: float) -> Arm:
    """One grid point, as a synthesized arm over the as-built topology.

    The bond RESISTANCE is taken from the base arm's own bonds rather than
    re-asserted from `PACKAGE_R_OHM`, so the sweep follows the arm it sweeps
    instead of drifting from it, and only the inductance moves along that
    axis.
    """
    base = ARMS_BY_NAME[SWEEP_BASE_ARM]
    if set(base.bonds) != set(TERMINAL_ORDER) or any(b is None for b in base.bonds.values()):
        raise RuntimeError(
            f"the sweep's base arm `{SWEEP_BASE_ARM}` no longer bonds all four supply "
            "terminals through an impedance -- the swept topology is not the as-built "
            "one any more; re-derive the sweep before running it."
        )
    if l_mult < 0.0 or rsubx_ohm <= 0.0:
        raise RuntimeError(
            f"sweep point ({l_mult}, {rsubx_ohm}) is not physical: the inductance "
            "multiplier must be >= 0 and the substrate link must be > 0 Ohm"
        )
    bonds = {t: Bond(b.r_ohm, b.l_h * l_mult) for t, b in base.bonds.items()}
    l_h = PACKAGE_L_H * l_mult
    return Arm(
        name=sweep_arm_name(l_mult, rsubx_ohm),
        summary=(
            f"as-built `{SWEEP_BASE_ARM}` topology at {l_mult:g}x DR-015's bond "
            f"inductance (L = {l_h * 1e9:.3f} nH per terminal, R unchanged at "
            f"{PACKAGE_R_OHM * 1e3:.1f} mOhm) and a lumped substrate link "
            f"R_SUBX = {rsubx_ohm:g} Ohm"
        ),
        bonds=bonds,
        substrate=(("RSUBX", GND_DIE, "VGND", rsubx_ohm),),
    )


def sweep_arms(l_mults: tuple[float, ...], rsubx_values: tuple[float, ...]) -> list[Arm]:
    """The grid, cheapest axis first: an inductance-free bond has nothing to
    ring, so running the L ladder in ascending order front-loads the points
    that finish quickly and leaves a partially-completed campaign (which
    `--log-cache` can resume) as useful as possible."""
    return [sweep_arm(m, r) for m in l_mults for r in rsubx_values]


def sweep_anchor_matches_base_arm() -> bool:
    """Is the `(1x, DR-015's R_SUBX)` grid point electrically the committed
    `package` arm?

    It must be: that point is the sweep's tie to the campaign's existing
    arm-comparison record, and the whole reading of the grid is "how far does
    the answer move as you walk away from DR-015's assumption point". If a
    later edit made the anchor a different network, the sweep would still run
    and still write a plausible record -- while no longer being anchored to
    anything. Compared on the emitted CARDS (comments excluded, since they
    carry the arm's name), which is the level at which "electrically the same
    deck" is a fact rather than an intention.
    """
    anchor = [
        line
        for line in arm_network_lines(sweep_arm(1.0, R_SUBX_OHM))
        if line and not line.startswith("*")
    ]
    base = [
        line
        for line in arm_network_lines(ARMS_BY_NAME[SWEEP_BASE_ARM])
        if line and not line.startswith("*")
    ]
    return anchor == base


# --------------------------------------------------------------------------
# The bounded null-option substrate sweep (`--null-sweep`, issue #409)
# --------------------------------------------------------------------------
# WHAT GAP THIS CLOSES. DR-015's Consequences section makes a claim about the
# `no-gnd-pad` arm that nothing in this repo had measured:
#
#     "The `no-gnd-pad` arm ... is *entirely* a function of `R_SUB`: with a
#      small `R_SUB` it looks harmless, with a large one it looks fatal."
#
# That is two predictions ("harmless", "fatal") about magnitudes this campaign
# has only ever run at ONE value. The arm-comparison record priced the null
# option at DR-015's assumed 30 Ohm; the 2-D `--sweep` box moved a substrate
# resistance but on the AS-BUILT `package` topology, where `GND` has a bond of
# its own and the substrate link is a secondary shunt rather than a return. So
# the sensitivity DR-015 asserts is still, at this point, an assertion.
#
# WHAT IS SWEPT, AND WHY IT IS THE ELEMENT DR-015 MEANS. The base deck is
# `no-gnd-pad`: `GND` has no bond, so the analog ground's ONLY path to the
# board is the lumped resistor between `GND_DIE` and `VGND` and then out
# through `VGND`'s own bond. In that topology that one resistor is
# simultaneously both of DR-015 item 2's stand-ins -- it sits "between the
# analog and digital ground die nodes" (`R_SUBX`'s definition) AND it is the
# whole substrate-only ground RETURN (`R_SUB`'s role). The deck instance is
# named `RSUBX` because that is the node pair it spans, and this sweep moves
# that instance; the record says both things rather than letting one name be
# read as the other. DR-015 sets both stand-ins to 30 Ohm, so at the anchor
# point the distinction costs nothing numerically -- it is a naming precision,
# not a change of magnitude.
#
# WHY THIS IS NOT THE 2-D SWEEP AGAIN. `--sweep` moves `R_SUBX` on a deck
# where `GND` is bonded through ~102 mOhm; a decade of change in a 30 Ohm
# shunt next to a 0.1 Ohm bond barely moves the analog ground. Here the same
# element carries the entire return current. Same constant, same decade,
# structurally different experiment.
#
# ONE AXIS, NOT TWO, ON PURPOSE. Crossing this with the bond-inductance
# ladder would be a second 2-D box and would confound the question: the point
# of a null-option sweep is what the REJECTED topology costs as the substrate
# assumption moves, with every other element held at DR-015's stated values.
# The three bonded terminals keep DR-015's R+L exactly, so each point differs
# from the committed `no-gnd-pad` arm in one element and from its neighbours
# in one element (DR-015 item 5).
NULL_SWEEP_BASE_ARM = "no-gnd-pad"

#: The lumped substrate resistance, in ohms: a decade either side of DR-015's
#: assumed 30 Ohm, matching the 2-D sweep's own bracket so the two boxes are
#: read on the same scale.
NULL_SWEEP_RSUBX_OHM: tuple[float, ...] = (3.0, 30.0, 300.0)


def null_sweep_arm_name(rsubx_ohm: float) -> str:
    """The swept point's arm name -- also its log/deck filename and its cache
    key. Prefixed distinctly from `sweep_arm_name()` so a point of this
    campaign can never collide with, or be mistaken for, a point of the 2-D
    box in a cache directory or a records listing."""
    return f"nullsweep-rsub{rsubx_ohm:g}"


def null_sweep_arm(rsubx_ohm: float) -> Arm:
    """One swept point: DR-012's rejected topology at one substrate magnitude.

    The bonds are taken from the base arm itself rather than re-asserted from
    `PACKAGE_R_OHM`/`PACKAGE_L_H`, so this sweep follows the arm it sweeps
    instead of drifting from it, and only the substrate resistance moves.
    """
    base = ARMS_BY_NAME[NULL_SWEEP_BASE_ARM]
    if "GND" in base.bonds:
        raise RuntimeError(
            f"the null sweep's base arm `{NULL_SWEEP_BASE_ARM}` now gives `GND` a bond "
            "of its own -- the swept topology is not DR-012's rejected null option any "
            "more, and its substrate resistor is no longer the analog ground's only "
            "return; re-derive the sweep before running it."
        )
    if len(base.substrate) != 1:
        raise RuntimeError(
            f"the null sweep's base arm `{NULL_SWEEP_BASE_ARM}` carries "
            f"{len(base.substrate)} lumped substrate elements, not one -- this sweep "
            "moves a single resistor and cannot say which one is the return."
        )
    if rsubx_ohm <= 0.0:
        raise RuntimeError(
            f"null-sweep point ({rsubx_ohm}) is not physical: a substrate resistance "
            "must be > 0 Ohm"
        )
    inst, node_a, node_b, _ohm = base.substrate[0]
    return Arm(
        name=null_sweep_arm_name(rsubx_ohm),
        summary=(
            f"DR-012's rejected `{NULL_SWEEP_BASE_ARM}` topology (GND unbonded) with "
            f"its lumped substrate return at {rsubx_ohm:g} Ohm; the other three "
            f"terminals keep DR-015's R+L unchanged"
        ),
        bonds=dict(base.bonds),
        substrate=((inst, node_a, node_b, rsubx_ohm),),
    )


def null_sweep_arms(rsubx_values: tuple[float, ...]) -> list[Arm]:
    """The ladder, in the order given. Unlike the 2-D box there is no known
    cheap-first ordering to exploit: the cost of this topology is set by how
    hard its ground rings, which is not monotone in the return resistance, so
    the ladder runs in the order the caller stated it."""
    return [null_sweep_arm(r) for r in rsubx_values]


def null_sweep_anchor_matches_base_arm() -> bool:
    """Is the `R = DR-015's value` point electrically the committed
    `no-gnd-pad` arm?

    Same contract, and same reason, as `sweep_anchor_matches_base_arm()`: that
    point is this sweep's tie to the arm-comparison record that already priced
    the null option, and without the tie the ladder would still run and still
    write a plausible record while being anchored to nothing.
    """
    anchor = [
        line
        for line in arm_network_lines(null_sweep_arm(R_SUBX_OHM))
        if line and not line.startswith("*")
    ]
    base = [
        line
        for line in arm_network_lines(ARMS_BY_NAME[NULL_SWEEP_BASE_ARM])
        if line and not line.startswith("*")
    ]
    return anchor == base


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
    annotated "(unverified -- non-volare layout)". `toolchain.check_env()`
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


def run_campaign(
    arms: list[Arm],
    corners_mode: bool,
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

    if corners_mode:
        grid = corners_mod.ratified_oat_grid(
            NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )
    else:
        grid = [BASELINE_CORNER]

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
# Evidence record
# --------------------------------------------------------------------------
def _mv(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e3:.3f}"


def _ua(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 1e6:.3f}"


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


def invocation_line(arm_names: list[str], corners_mode: bool, supersedes: str) -> str:
    """The command that actually produced this record, not a canonical stand-in.

    `sim/check_spec_coverage.py` reads the `Written by` footer to check a record
    against its indexed runner, and `sim/README.md` makes records the
    non-rewritable half of the evidence trail -- so the footer states the real
    arm list and the real flags. A reader who runs exactly this line gets
    exactly this record's arm set back.

    WHAT BELONGS HERE, AND WHAT DELIBERATELY DOES NOT. Flags that change what
    was simulated (`--arms`, `--corners`) or which record this one replaces
    (`--supersedes`) are part of this record's identity and are stated. A flag
    that only changes how the run was *scheduled* is not: `--log-cache` is a
    restart mechanism whose reuse is identity-gated on deck sha256, open_pdks
    commit and ngspice version, so it cannot change a number, and its argument
    is one machine's scratch directory rather than anything about the
    experiment. Naming it here would break the footer twice over -- a
    placeholder such as `<DIR>` is not runnable as written, and
    `check_spec_coverage.py` requires every token after the runner path to
    appear in the indexed bench's documented `cold_start`
    (`cold-start-record-mismatch`), which a machine-local path can never
    satisfy. Which runs did reuse a stored log IS provenance this record
    carries: the wall-clock table marks those rows individually.

    That gate binds the other direction too. A record minted with an `--arms`
    list the indexed `cold_start` does not document needs its own bench entry in
    `sim/spec-coverage.json` -- the shape `sar-sequencer-behavioral` already
    uses for its `--corners` variant -- rather than a footer softened to fit.
    """
    parts = [RUNNER_REL]
    if arm_names != [arm.name for arm in ARMS]:
        parts.append("--arms " + ",".join(arm_names))
    if corners_mode:
        parts.append("--corners")
    parts.append("--record")
    if supersedes:
        parts.append(f"--supersedes {supersedes}")
    return " ".join(parts)


def write_record(
    points: list[dict],
    dut_netlist_text: str,
    corners_mode: bool,
    arm_names: list[str],
    supersedes: str = "",
) -> Path:
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR,
        dut_netlist_text,
        "corners",
        {f"{p['point_id'].replace('@', '__')}.log": p["log_text"] for p in points},
    )
    deck_dir = EXPERIMENT_DIR / "corners" / prov.record_id
    for p in points:
        (deck_dir / f"{p['point_id'].replace('@', '__')}.cir").write_text(p["deck_text"])

    arms_run = [name for name in (a.name for a in ARMS) if any(p["arm"] == name for p in points)]
    corner_ids = sorted({p["corner_id"] for p in points})
    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})
    controls = {p["corner_id"]: p for p in points if p["arm"] == CONTROL_ARM}

    a = lines.append
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- **Power** (DRAFT row), "
        "INFORMATIONAL only, and the evidence "
        "`spec/decision-records/DR-012-analog-ground-pad.md`'s open item "
        "(\"the impedance argument is unmeasured\", issue #378) asks for. It "
        "edits no spec row, proposes no power target, and grades nothing against "
        "a ratified line. What it measures is a DIFFERENCE: the same stimulus, "
        f"the same DUT, {len(arms_run)} supply-return networks."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with two "
        "TESTBENCH-ONLY transformations that are never written back to `design/`: "
        "the DUT's `GND` net is renamed `GND_DIE` (a net named `GND` is ngspice's "
        "global node 0 and would short out every series element this campaign "
        "inserts), and the committed fragment's `VVDD`/`VVPWR`/`VVGND` source "
        "cards are re-pointed to board-side nodes on the arms that bond them "
        "through an impedance. Source instance names, the `.tran` card, the "
        "clock/reset/input schedule and every code and phase `.meas` card are "
        "used verbatim."
    )
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Arms**: {len(arms_run)} supply-return networks "
        + ", ".join(f"`{name}`" for name in arms_run)
        + f" x {len(corner_ids)} corner point(s) = {len(points)} transient runs. "
        f"`{CONTROL_ARM}` is the control: it is exactly what every existing "
        "`sim/` campaign runs today."
    )
    a(
        "- **Stimulus**: `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice`, unmodified except for the supply "
        f"source cards' nodes -- `f_clk = {tb.F_CLK_HZ / 1e6:g} MHz` (DR-006 worst "
        f"case), {tb.N_CONVERSIONS} back-to-back conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods, the first discarded as start-up, "
        "the remaining five carrying DC differential inputs of "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + "."
    )
    a("")

    a("## The package-style assumption (DR-015)")
    a("")
    lines.extend(_assumption_lines())
    a("")
    a(
        "**What the substrate arms can and cannot claim.** There is no extracted "
        "substrate network in this repo, and this campaign does not create one. "
        "`R_SUB`/`R_SUBX` are single lumped resistors standing in for a "
        "distributed, layout-dependent network; their magnitude is taken from "
        "DR-012's own prose, not from `klt extract`, not from measurement, and "
        "not from anyone else's data. A result below that depends on them is "
        "evidence about *a* resistive return of that order, not a statement about "
        "*this* die's substrate. The R+L values are a stated package-style "
        "assumption (DR-015), not a measurement of any package."
    )
    a("")

    a("## The arms, as networks")
    a("")
    lines.extend(arm_table_lines([ARMS_BY_NAME[name] for name in arms_run]))
    a("")
    a(
        "Read the ladder, not any single row: `package` vs `package-r-only` "
        "isolates **bond inductance** (identical resistance, identical terminals, "
        "one element different); `package-r-only` vs `ideal` isolates the bond's "
        "own **resistance**; `substrate` answers a different question -- what an "
        "**on-die-only** resistive return of DR-012's stated order would cost -- "
        "and is NOT an ablation of `package`, because its resistance is ~"
        f"{R_SUB_OHM / PACKAGE_R_OHM:.0f}x larger. `no-gnd-pad` is DR-012's "
        "rejected null option, and per DR-015's own open item it is a function of "
        "`R_SUB` above all else, so it must always be read as \"at this assumed "
        "magnitude\"; against `package` it is itself a strict one-element "
        "ablation -- same three bonded terminals, same substrate link, the only "
        "difference is whether `GND` has a bond of its own -- so that pair, and "
        "only that pair, prices the option DR-012 rejected against the option it "
        "chose."
    )
    a("")

    a("## Captured code per arm (the comparison)")
    a("")
    header = "| corner-id | arm | " + " | ".join(
        f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)})" for f in tb.INPUT_FRACTIONS
    ) + " | worst \\|delta code\\| vs `ideal` (mid-scale) |"
    a(header)
    a("|---" * (len(tb.INPUT_FRACTIONS) + 3) + "|")
    for cid in corner_ids:
        for name in arms_run:
            p = next((q for q in points if q["corner_id"] == cid and q["arm"] == name), None)
            if p is None:
                continue
            control = controls.get(cid)
            deltas = code_delta(p, control) if control else {}
            cells = []
            for cv in p["conversions"]:
                code = "MISSING" if cv["code"] is None else str(cv["code"])
                delta = deltas.get(cv["conversion"])
                suffix = "" if delta is None else f" ({delta:+d})"
                if name == CONTROL_ARM:
                    suffix = ""
                cells.append(f"{code}{suffix}")
            worst = "-- (control)" if name == CONTROL_ARM else worst_mid_scale_delta(p, control)
            a(f"| `{cid}` | `{name}` | " + " | ".join(cells) + f" | {worst} |")
    a("")
    a(
        "Each cell is the captured code, and in parentheses its difference from "
        f"the `{CONTROL_ARM}` arm at the same corner. The `+-0.78*V_REF` columns "
        "are reported but EXCLUDED from the worst-delta column: "
        "`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` "
        "already records those two inputs as wrong by ~100 LSB at every corner "
        "(issue #267, common-mode saturation at large differential input, still "
        "open), so a change there cannot be attributed to supply impedance."
    )
    a("")

    a("## Die-side rail excursion over one steady-state conversion")
    a("")
    a(
        "| corner-id | arm | "
        + " | ".join(f"{name} pp (mV)" for name, _n, _l in RAIL_PROBES)
        + " | GND_die min (mV) | GND_die max (mV) |"
    )
    a("|---" * (len(RAIL_PROBES) + 4) + "|")
    for cid in corner_ids:
        for name in arms_run:
            p = next((q for q in points if q["corner_id"] == cid and q["arm"] == name), None)
            if p is None:
                continue
            cells = [_mv(p["extras"].get(f"{probe}_pp")) for probe, _n, _l in RAIL_PROBES]
            a(
                f"| `{cid}` | `{name}` | "
                + " | ".join(cells)
                + f" | {_mv(p['extras'].get('gnd_die_min'))} "
                f"| {_mv(p['extras'].get('gnd_die_max'))} |"
            )
    a("")
    a(
        "`pp` is the peak-to-peak excursion of the DIE-side node over the same "
        "steady-state conversion the supply currents are averaged over. The "
        f"`{CONTROL_ARM}` arm's ground rows are the mechanical control: an ideal "
        "source holds the die node at exactly 0 V, so a nonzero excursion there "
        "would mean the arm network is not doing what this record says it does. "
        "`GND_die` is the comparator's own reference (DR-012: \"during "
        "regeneration its own ground *is* the reference its differential pair's "
        "imbalance is resolved against\")."
    )
    a("")

    a("## Average rail current over the same conversion")
    a("")
    a(
        "| corner-id | arm | I(VDD) (uA) | I(VPWR) (uA) | I(GND) (uA) | "
        "I(VREFP) (uA) | I(VCM) (uA) | total power (uW) |"
    )
    a("|---|---|---|---|---|---|---|---|")
    for cid in corner_ids:
        for name in arms_run:
            p = next((q for q in points if q["corner_id"] == cid and q["arm"] == name), None)
            if p is None:
                continue
            i_gnda = p["extras"].get("i_gnda")
            a(
                f"| `{cid}` | `{name}` | {_ua(p['currents'].get('i_vdd'))} | "
                f"{_ua(p['currents'].get('i_vpwr'))} | "
                f"{'n/a (no bond)' if i_gnda is None else _ua(abs(i_gnda))} | "
                f"{_ua(p['currents'].get('i_vrefp'))} | "
                f"{_ua(p['currents'].get('i_vcm'))} | "
                f"{p['power_w'] * 1e6:.3f} |"
            )
    a("")

    a("## Findings")
    a("")
    for line in findings_lines(points, controls, arms_run, corner_ids):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    a("| corner-id | arm | wall clock (s) | x the `ideal` arm at the same corner |")
    a("|---|---|---|---|")
    for cid in corner_ids:
        base = controls.get(cid, {}).get("wall_s")
        for name in arms_run:
            p = next((q for q in points if q["corner_id"] == cid and q["arm"] == name), None)
            if p is None:
                continue
            ratio = "--" if not base else f"{p['wall_s'] / base:.2f}x"
            note = " (log reused from cache)" if p.get("reused") else ""
            a(f"| `{cid}` | `{name}` | {p['wall_s']:.0f}{note} | {ratio} |")
    a("")
    if any(p.get("reused") for p in points):
        a(
            "Rows marked **log reused from cache** were not re-simulated for this "
            "record: `--log-cache` found a stored ngspice log whose deck sha256, "
            "volare-verified open_pdks commit and ngspice version all matched the "
            "run about to be made, and reused it rather than repeating a "
            "tens-of-minutes transient after an interruption. The reported wall "
            "clock is the one measured when that run actually executed. A mismatch "
            "on any identity field re-simulates, and a host that cannot verify its "
            "own open_pdks commit or ngspice version never reuses at all, so a "
            "reused log is provably the log of this same deck on this same "
            "toolchain -- the cache is a restart mechanism, not a route by which a "
            "stale number reaches a record."
        )
        a("")
    a(
        "Reported because it is the load-bearing input to the corner-subset "
        "justification below, and because it is itself a finding: an undecoupled "
        "series inductance against the die's own capacitance rings well above the "
        "clock rate and forces the transient solver's timestep down, so a bonded "
        "arm costs materially more than the ideal one for the same simulated span. "
        "These are wall-clock seconds on a shared, contended host, so they are an "
        "order-of-magnitude ratio between arms rather than a benchmark of either."
    )
    a("")

    omitted_arms = [arm.name for arm in ARMS if arm.name not in arms_run]
    if omitted_arms:
        a("## Arms this record does not contain")
        a("")
        a(
            "The runner implements "
            + ", ".join(f"`{arm.name}`" for arm in ARMS)
            + "; this record ran "
            + ", ".join(f"`{name}`" for name in arms_run)
            + " and omitted "
            + ", ".join(f"`{name}`" for name in omitted_arms)
            + ". Stated here for the same reason `sim/README.md` requires a "
            "corner subset to be justified: an unexplained omission is not a "
            "valid record, and a reader must not have to infer that an arm the "
            "code offers was skipped."
        )
        a("")
        for name in omitted_arms:
            note = ARM_OMISSION_NOTES.get(name)
            if note:
                a(f"- **`{name}`** is {note}")
        a("")

    if not corners_mode:
        lines.extend(
            subset_corner_lines(
                corner_ids,
                "the arm comparison",
                f"{len(arms_run)} arms",
                len(arms_run),
                "a mechanism comparison at the baseline corner",
            )
        )

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per run",
                "runs": f"{len(points)} ({len(arms_run)} arms x {len(corner_ids)} corner points)",
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "package assumption": (
                    f"R = {PACKAGE_R_OHM * 1e3:.1f} mOhm, L = {PACKAGE_L_H * 1e9:.3f} nH "
                    f"per bonded terminal; R_SUB = {R_SUB_OHM:g} Ohm, "
                    f"R_SUBX = {R_SUBX_OHM:g} Ohm (DR-015)"
                ),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(invocation_line(arm_names, corners_mode, supersedes), supersedes)
    )

    path = evidence.close_record(prov, lines, "Record")
    (EXPERIMENT_DIR / "records" / "LATEST").write_text(f"{prov.record_id}.md\n")
    return path


def subset_corner_lines(
    corner_ids: list[str],
    what_ran: str,
    decks_label: str,
    n_decks: int,
    what_it_is_instead: str,
) -> list[str]:
    """`sim/README.md`'s required justification for running a subset of the
    ratified corner set, shared by every record this runner writes.

    It is one argument, not one per record mode: the three constraints below
    are properties of the HOST and of the cost of one whole-ADC transient, so
    a second record mode that also runs at the baseline corner must state the
    same three and must not get to paraphrase them into something weaker.
    Only the sentence naming what ran, and the cost arithmetic, differ.
    """
    out = [
        "## Subset-corner justification (`sim/README.md`)",
        "",
        (
            f"This record runs {what_ran} at {len(corner_ids)} point(s) of the "
            f"ratified corner set ({', '.join('`' + c + '`' for c in corner_ids)}), "
            "not all nine. Three separate constraints bind, and none of them is a "
            "judgement that the corners do not matter:"
        ),
        "",
        (
            "- **Host policy.** The machine this record was produced on is a "
            "shared dispatch worker whose operating rules forbid running a "
            "multi-corner ngspice grid locally; a grid there must be expressed as "
            "a `klt sim` request and submitted to an EDA batch fleet. Sequential "
            "single-corner runs are the shape those rules do allow, and that is "
            "what the table above is."
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
            f"- **Cost.** The nine-point ratified grid across {decks_label} is "
            f"{9 * n_decks} whole-ADC transients. At the per-run cost measured "
            "above that is a campaign in its own right, not a longer version of "
            "this one."
        ),
        "",
        (
            "So the ratified-grid run is **deferred, not skipped**: the runner "
            "already implements it (`--corners`, the nine-point "
            "`ratified_oat_grid()` x the decks) and this experiment's README names "
            "the exact command. What it needs is a host whose ngspice satisfies "
            "the pin and whose policy allows a grid -- not more code. Until then, "
            f"no statement in this record is a corner-worst-case claim; it is "
            f"{what_it_is_instead}."
        ),
        "",
    ]
    return out


def findings_lines(
    points: list[dict], controls: dict[str, dict], arms_run: list[str], corner_ids: list[str]
) -> list[str]:
    out: list[str] = []
    for name in arms_run:
        if name == CONTROL_ARM:
            continue
        deltas = []
        bounces = []
        for cid in corner_ids:
            p = next((q for q in points if q["corner_id"] == cid and q["arm"] == name), None)
            control = controls.get(cid)
            if p is None or control is None:
                continue
            d = worst_mid_scale_delta(p, control)
            if d is not None:
                deltas.append(d)
            pp = p["extras"].get("gnd_die_pp")
            if pp is not None:
                bounces.append(pp)
        worst_delta = max(deltas) if deltas else None
        worst_bounce = max(bounces) if bounces else None
        out.append(
            f"- **`{name}`**: worst mid-scale code change vs `{CONTROL_ARM}` = "
            + ("n/a" if worst_delta is None else f"**{worst_delta} LSB**")
            + "; worst die-side analog-ground excursion = "
            + ("n/a" if worst_bounce is None else f"**{worst_bounce * 1e3:.3f} mV** "
               f"peak-to-peak ({worst_bounce / (2.0 * NOMINAL_SUPPLY_V / 2**tb.N_BITS):.3f} "
               "LSB at the nominal supply)")
            + "."
        )
    out.extend(ablation_lines(points, arms_run, corner_ids))
    out.extend(gnd_pad_ablation_lines(points, arms_run, corner_ids))
    missing_points = [p["point_id"] for p in points if p["missing"]]
    if missing_points:
        out.append(
            "- **Incomplete runs** (some `.meas` value did not come back): "
            + ", ".join(f"`{pid}`" for pid in missing_points)
            + " -- reported rather than dropped."
        )
    return out


def ablation_lines(points: list[dict], arms_run: list[str], corner_ids: list[str]) -> list[str]:
    """The bond-inductance ablation, stated as a difference between two arms
    that differ in exactly one element.

    `package` and `package-r-only` carry the same per-terminal resistance on the
    same four terminals; the only difference is the series `L`. So the change
    between them is bond inductance's own contribution -- a number that isolates
    a single mechanism rather than comparing two whole grounding schemes.
    Deliberately NOT computed against `substrate`: that arm's resistance is ~300x
    the package resistance, so it differs from `package` in two elements at once
    and a difference against it would confound them.

    Whether it is the record's *only* such number depends on which arms ran, so
    the emitted sentence is conditional rather than an unconditional uniqueness
    claim: a record that also carries `no-gnd-pad` alongside `package` gets a
    second one-element ablation from `gnd_pad_ablation_lines()` below, and
    records are append-only evidence -- a false "the only" written into one can
    be corrected only by minting a superseding record.
    """
    if not {"package", "package-r-only"} <= set(arms_run):
        return [
            "- **Bond-inductance ablation not available in this record**: it needs "
            "both the `package` and `package-r-only` arms, and this run did not "
            "include both."
        ]
    # `package` is guaranteed present by the guard above, so the ground-pad
    # ablation is reported for this record exactly when `no-gnd-pad` also ran
    # (the same condition `gnd_pad_ablation_lines()` keys its own output on).
    standing = (
        "This and the ground-pad ablation below (`no-gnd-pad` vs `package`, "
        "which isolates the other single element in this family of decks) are "
        "the two single-mechanism numbers in this record."
        if "no-gnd-pad" in arms_run
        else "This is the only single-mechanism number in this record."
    )
    out: list[str] = []
    for cid in corner_ids:
        full = next((q for q in points if q["corner_id"] == cid and q["arm"] == "package"), None)
        r_only = next(
            (q for q in points if q["corner_id"] == cid and q["arm"] == "package-r-only"), None
        )
        if full is None or r_only is None:
            continue
        delta = worst_mid_scale_delta(full, r_only)
        pp_full = full["extras"].get("gnd_die_pp")
        pp_r = r_only["extras"].get("gnd_die_pp")
        pp_txt = (
            "n/a"
            if pp_full is None or pp_r is None
            else f"{pp_full * 1e3:.3f} mV vs {pp_r * 1e3:.3f} mV"
        )
        out.append(
            f"- **Bond-inductance ablation at `{cid}`** (`package` vs "
            "`package-r-only`, identical except for the series `L`): worst "
            "mid-scale code change = "
            + ("n/a" if delta is None else f"**{delta} LSB**")
            + f"; analog-ground excursion {pp_txt}. {standing}"
        )
    return out


def gnd_pad_ablation_lines(
    points: list[dict], arms_run: list[str], corner_ids: list[str]
) -> list[str]:
    """The ground-PAD ablation: `no-gnd-pad` against `package`.

    This is the pair DR-012 actually decided between. The two arms carry the
    same package R+L on `VDD`, `VPWR` and `VGND`, the same lumped `R_SUBX`
    between the two ground die nodes, and the same stimulus; the ONLY
    difference is whether `GND` has a bond of its own. So the difference
    between them is the drawn analog ground pad's own contribution and nothing
    else -- the price of the option DR-012 rejected, at this corner and at
    DR-015's assumed magnitudes.

    Deliberately NOT computed against `ideal` or `substrate`: `ideal` differs
    from `no-gnd-pad` in four elements at once, and `substrate` differs in the
    bond inductance as well as the ground path, so neither difference would
    isolate the pad. Read together with the bond-inductance ablation above,
    which isolates the other single element in the same family of decks.

    `no-gnd-pad` is a function of `R_SUB`/`R_SUBX` above all else (DR-015's own
    open item), so every line this produces is stated as "at this assumed
    magnitude" rather than as a prediction for this die.
    """
    if "no-gnd-pad" not in arms_run:
        return []
    if "package" not in arms_run:
        return [
            "- **Ground-pad ablation not available in this record**: it needs both "
            "the `package` and `no-gnd-pad` arms (they differ in exactly one "
            "element -- whether `GND` is bonded), and this run did not include "
            "both. The `no-gnd-pad` rows above are therefore a grounding scheme's "
            "own numbers, not a priced difference against the as-built shape."
        ]
    out: list[str] = []
    for cid in corner_ids:
        null_opt = next(
            (q for q in points if q["corner_id"] == cid and q["arm"] == "no-gnd-pad"), None
        )
        as_built = next(
            (q for q in points if q["corner_id"] == cid and q["arm"] == "package"), None
        )
        if null_opt is None or as_built is None:
            continue
        delta = worst_mid_scale_delta(null_opt, as_built)
        pp_null = null_opt["extras"].get("gnd_die_pp")
        pp_built = as_built["extras"].get("gnd_die_pp")
        if pp_null is None or pp_built is None:
            pp_txt = "n/a"
        else:
            pp_txt = f"{pp_null * 1e3:.3f} mV vs {pp_built * 1e3:.3f} mV"
            if pp_built > 0.0:
                pp_txt += f" ({pp_null / pp_built:.1f}x)"
        out.append(
            f"- **Ground-pad ablation at `{cid}`** (`no-gnd-pad` vs `package`, "
            "identical except that `GND` has no bond of its own): worst mid-scale "
            "code change = "
            + ("n/a" if delta is None else f"**{delta} LSB**")
            + f"; die-side analog-ground excursion {pp_txt}. This is the price of "
            "the option DR-012 rejected, measured against the option it chose, at "
            f"`R_SUB` = {R_SUB_OHM:g} Ohm / `R_SUBX` = {R_SUBX_OHM:g} Ohm -- a "
            "LUMPED stand-in (DR-015), so it is a number about a resistive return "
            "of that order and not about this die's substrate."
        )
    return out


# --------------------------------------------------------------------------
# The sweep's own record
# --------------------------------------------------------------------------
def sweep_invocation_line(
    l_mults: tuple[float, ...], rsubx_values: tuple[float, ...], supersedes: str
) -> str:
    """The `--sweep` counterpart of `invocation_line()`, under the same rules:
    a flag that changes what was simulated is stated, one that only changes
    how the run was scheduled (`--log-cache`) is not. The axis flags appear
    only when the run departed from the documented box, so the default sweep's
    footer is exactly the command `sim/spec-coverage.json` indexes."""
    parts = [RUNNER_REL, "--sweep"]
    if tuple(l_mults) != SWEEP_L_MULTIPLIERS:
        parts.append("--sweep-l-mult " + ",".join(f"{m:g}" for m in l_mults))
    if tuple(rsubx_values) != SWEEP_RSUBX_OHM:
        parts.append("--sweep-rsubx " + ",".join(f"{r:g}" for r in rsubx_values))
    parts.append("--record")
    if supersedes:
        parts.append(f"--supersedes {supersedes}")
    return " ".join(parts)


def _sweep_point(points: list[dict], l_mult: float, rsubx_ohm: float) -> dict | None:
    name = sweep_arm_name(l_mult, rsubx_ohm)
    return next((p for p in points if p["arm"] == name), None)


def sweep_matrix_lines(
    points: list[dict],
    l_mults: tuple[float, ...],
    rsubx_values: tuple[float, ...],
    cell: Callable[[dict], str],
) -> list[str]:
    """The grid as a matrix: one row per bond-inductance multiplier, one
    column per substrate-link resistance. Rendered this way, not as a flat
    list, because the whole point of a 2-D sweep is that a reader can read one
    axis at a time -- a row is a one-element `L` family and a column is a
    one-element `R_SUBX` family (DR-015 item 5)."""
    out = [
        "| bond `L` (x DR-015) | " + " | ".join(f"`R_SUBX` = {r:g} Ohm" for r in rsubx_values) + " |",
        "|---" * (len(rsubx_values) + 1) + "|",
    ]
    for m in l_mults:
        cells = []
        for r in rsubx_values:
            p = _sweep_point(points, m, r)
            cells.append("(not run)" if p is None else cell(p))
        out.append(
            f"| **{m:g}x** ({PACKAGE_L_H * m * 1e9:.3f} nH) | " + " | ".join(cells) + " |"
        )
    return out


def sweep_findings_lines(
    points: list[dict],
    control: dict | None,
    l_mults: tuple[float, ...],
    rsubx_values: tuple[float, ...],
) -> list[str]:
    """What the swept box says, as differences rather than as a table reading.

    Every bullet is a statement about a MAGNITUDE, because that is the gap
    DR-015 opened: its single assumption point can say "not fatal here", and
    only a sweep can say "and it stays that way out to N x that assumption,
    at this corner".
    """
    out: list[str] = []

    out.append(
        "- **The grid is anchored to the committed arm comparison.** Its "
        f"`{sweep_arm_name(1.0, R_SUBX_OHM)}` point is, card for card, the "
        f"`{SWEEP_BASE_ARM}` arm this campaign already recorded at this corner: "
        f"same per-terminal R+L, same lumped `R_SUBX = {R_SUBX_OHM:g} Ohm`, same "
        "stimulus. "
        + (
            "Checked at record-write time (`sweep_anchor_matches_base_arm()`), so "
            "the sweep is tied to the existing record rather than merely described "
            "as being."
            if sweep_anchor_matches_base_arm()
            else "**This check FAILED at record-write time** -- the anchor point is "
            "no longer the as-built arm, so nothing below may be read as a walk "
            "away from DR-015's assumption point."
        )
    )

    # The L axis, read one substrate value at a time (a one-element family).
    for r in rsubx_values:
        cells = []
        for m in l_mults:
            p = _sweep_point(points, m, r)
            pp = None if p is None else p["extras"].get("gnd_die_pp")
            cells.append("n/a" if pp is None else f"{pp * 1e3:.3f} mV")
        out.append(
            f"- **Bond inductance at `R_SUBX = {r:g} Ohm`**: die-side analog-ground "
            "excursion "
            + " -> ".join(cells)
            + " as `L` goes "
            + " -> ".join(f"{m:g}x" for m in l_mults)
            + ". Only `L` moves along this row, so the change is the bond "
            "inductance's own contribution (DR-015 item 5)."
        )

    # The substrate axis, read one inductance at a time.
    for m in l_mults:
        cells = []
        for r in rsubx_values:
            p = _sweep_point(points, m, r)
            pp = None if p is None else p["extras"].get("gnd_die_pp")
            cells.append("n/a" if pp is None else f"{pp * 1e3:.3f} mV")
        out.append(
            f"- **Substrate link at `L = {m:g}x`**: die-side analog-ground excursion "
            + " -> ".join(cells)
            + " as `R_SUBX` goes "
            + " -> ".join(f"{r:g} Ohm" for r in rsubx_values)
            + ". Only `R_SUBX` moves along this column -- this is how hard the "
            "p-substrate ties the analog and digital ground die nodes together, "
            "not a substrate RETURN resistance (see the scope section below)."
        )

    # Where, if anywhere, in this box a captured code moves.
    if control is not None:
        moved = []
        for m in l_mults:
            for r in rsubx_values:
                p = _sweep_point(points, m, r)
                if p is None:
                    continue
                delta = worst_mid_scale_delta(p, control)
                if delta:
                    moved.append((m, r, delta))
        if moved:
            first = min(moved, key=lambda t: (t[0], t[1]))
            out.append(
                "- **A mid-scale captured code moves inside this box.** The "
                f"smallest point at which it does is `L = {first[0]:g}x`, "
                f"`R_SUBX = {first[1]:g} Ohm` (worst mid-scale |delta code| = "
                f"**{first[2]} LSB** vs the `{CONTROL_ARM}` control); "
                f"{len(moved)} of {len(l_mults) * len(rsubx_values)} grid points "
                "move at least one mid-scale code. So the mechanism has a "
                "threshold within the swept magnitudes, and DR-015's assumption "
                "point is on one side of it at this corner."
            )
        else:
            out.append(
                "- **No mid-scale captured code moves anywhere in this box.** Every "
                f"grid point reproduces the `{CONTROL_ARM}` control's mid-scale "
                "codes exactly (worst |delta code| = **0 LSB**), out to "
                f"`L = {max(l_mults):g}x` DR-015's bond inductance and "
                f"`R_SUBX` from {min(rsubx_values):g} to {max(rsubx_values):g} Ohm. "
                "That is a **bounded null result**: the threshold this sweep went "
                "looking for is outside the box, not located inside it, and a "
                "wider box (or another corner) could still find one."
            )

    # The worst excursion anywhere in the box, in mV and in LSB.
    worst = None
    for m in l_mults:
        for r in rsubx_values:
            p = _sweep_point(points, m, r)
            pp = None if p is None else p["extras"].get("gnd_die_pp")
            if pp is not None and (worst is None or pp > worst[2]):
                worst = (m, r, pp)
    if worst is not None:
        lsb_v = 2.0 * NOMINAL_SUPPLY_V / 2**tb.N_BITS
        out.append(
            "- **Worst die-side analog-ground excursion in the box**: "
            f"**{worst[2] * 1e3:.3f} mV** peak-to-peak ({worst[2] / lsb_v:.3f} LSB at "
            f"the nominal supply) at `L = {worst[0]:g}x`, "
            f"`R_SUBX = {worst[1]:g} Ohm`. Whatever on-die decoupling the committed "
            "`design/sar_adc_top.spice` carries is in the deck (DR-016 added one "
            "`cap_mim_m3_1` per supply domain; DR-015 item 6's `no decoupling is "
            "modelled' premise held only before that). **No BOARD decoupling is "
            "modelled**, so the figure is still an upper bound rather than a "
            "prediction."
        )

    missing_points = [p["point_id"] for p in points if p["missing"]]
    if missing_points:
        out.append(
            "- **Incomplete runs** (some `.meas` value did not come back): "
            + ", ".join(f"`{pid}`" for pid in missing_points)
            + " -- reported rather than dropped."
        )
    return out


def write_sweep_record(
    points: list[dict],
    dut_netlist_text: str,
    l_mults: tuple[float, ...],
    rsubx_values: tuple[float, ...],
    supersedes: str = "",
) -> Path:
    """The `--sweep` record.

    A separate writer from `write_record()` on purpose: the two records make
    different claims and must not be able to borrow each other's sentences.
    `write_record()` compares NETWORKS at DR-015's assumption point; this one
    walks a bounded box AROUND that point on the as-built network, so its
    tables are matrices over the two swept axes and its findings are about
    magnitudes. What they do share -- the DR-015 assumption table, the
    subset-corner justification, the environment block, the footer rules --
    they share by calling the same helpers, so neither can drift into a softer
    version of the other's caveats.
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

    grid_points = [p for p in points if p["arm"] != CONTROL_ARM]
    corner_ids = sorted({p["corner_id"] for p in points})
    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})
    control = next((p for p in points if p["arm"] == CONTROL_ARM), None)

    a = lines.append
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- **Power** (DRAFT row), "
        "INFORMATIONAL only, and the evidence "
        "`spec/decision-records/DR-015-package-parasitic-assumption.md`'s open item "
        "(\"No `R`/`L` sweep ... a bounded 2-D sweep (bond inductance x substrate "
        "resistance) at one corner is the natural follow-up\", issue #409) asks "
        "for. It edits no spec row, proposes no power target, and grades nothing "
        "against a ratified line. What it measures is how far the campaign's "
        "existing answer MOVES as DR-015's two assumed magnitudes are walked "
        "away from, on the as-built supply-return network."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with two "
        "TESTBENCH-ONLY transformations that are never written back to `design/`: "
        "the DUT's `GND` net is renamed `GND_DIE` (a net named `GND` is ngspice's "
        "global node 0 and would short out every series element this campaign "
        "inserts), and the committed fragment's `VVDD`/`VVPWR`/`VVGND` source "
        "cards are re-pointed to board-side nodes. Source instance names, the "
        "`.tran` card, the clock/reset/input schedule and every code and phase "
        "`.meas` card are used verbatim."
    )
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Grid**: {len(l_mults)} bond-inductance multipliers x "
        f"{len(rsubx_values)} substrate-link resistances = {len(grid_points)} swept "
        f"points, plus the `{CONTROL_ARM}` control, at {len(corner_ids)} corner "
        f"point(s) = {len(points)} whole-ADC transients. Every swept point is the "
        f"as-built `{SWEEP_BASE_ARM}` topology (all four supply terminals bonded, "
        "DR-012's chosen shape) with exactly those two elements moved."
    )
    a(
        "- **Stimulus**: `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice`, unmodified except for the supply "
        f"source cards' nodes -- `f_clk = {tb.F_CLK_HZ / 1e6:g} MHz` (DR-006 worst "
        f"case), {tb.N_CONVERSIONS} back-to-back conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods, the first discarded as start-up, "
        "the remaining five carrying DC differential inputs of "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + "."
    )
    a("")

    a("## Why this record exists")
    a("")
    a(
        "[DR-015](../../../spec/decision-records/DR-015-package-parasitic-assumption.md) "
        "fixes ONE point in the space of package-style parasitics, and says in its "
        "own \"Alternatives considered\" that sweeping instead of fixing \"is the "
        "better experiment\" -- deferred only on cost. A single point can show "
        "whether the mechanism matters *at that magnitude*; it cannot find the "
        "magnitude at which it starts to. This record is that bounded sweep, at "
        "the baseline corner, on the as-built network, and it is the third item of "
        "[issue #409](https://github.com/2AMLogic/sky130-sar-adc/issues/409). It "
        "does not supersede the campaign's arm-comparison record: that record "
        "compares five NETWORKS at DR-015's assumption point, this one walks a box "
        "around that point on one of them, and both statements stand."
    )
    a("")

    a("## The package-style assumption (DR-015), and which of it is swept")
    a("")
    lines.extend(_assumption_lines())
    a("")
    a(
        "The sweep moves the **bond inductance** row (as a multiple of the stated "
        f"total, {PACKAGE_L_H * 1e9:.3f} nH per terminal) and the **substrate link "
        "`R_SUBX`** row. The bond RESISTANCE is held at DR-015's value throughout, "
        "so a row of the grid changes one element and a column changes one other "
        "-- which is what lets either be attributed to its own mechanism "
        "(DR-015 item 5) rather than reported as a comparison of two schemes."
    )
    a("")
    a(
        "**What the substrate axis is, and is not.** `R_SUBX` is the lumped "
        "stand-in for the p-substrate path that makes `GND` and `VGND` one "
        "extracted net (DR-012's own extraction evidence). Sweeping it asks how "
        "hard the substrate ties the two ground domains together, which is what "
        "decides how much of the digital ground's switching current comes back "
        "through the analog bond. It is **not** `R_SUB`, the substrate-only "
        "RETURN resistance -- that element appears only in the `substrate` and "
        "`no-gnd-pad` arms, not in the as-built network swept here, and the arm "
        "where it is load-bearing is the expensive one this campaign has not yet "
        "run. There is still no extracted substrate network in this repo; both are "
        "single lumped resistors standing in for a distributed, layout-dependent "
        "thing, so every number below is evidence about *a* return of that order, "
        "not about *this* die's substrate."
    )
    a("")

    a("## The swept points, as networks")
    a("")
    lines.extend(
        arm_table_lines(
            [ARMS_BY_NAME[CONTROL_ARM]] + [sweep_arm(m, r) for m in l_mults for r in rsubx_values],
            substrate_note=False,
        )
    )
    a(
        f"The `{CONTROL_ARM}` row is the control every delta below is taken "
        "against: ideal sources at the die, the zero-impedance case every other "
        "`sim/` campaign runs. Each swept row also carries its own lumped "
        "`R_SUBX` between the analog and digital ground DIE nodes, which is the "
        "second axis; in `ideal` both ends of that link are held at 0 V, so it "
        "carries no current and the control stays a true zero-impedance reference."
    )
    a("")

    a("## Die-side analog-ground excursion over the swept box")
    a("")
    lines.extend(
        sweep_matrix_lines(
            points,
            l_mults,
            rsubx_values,
            lambda p: f"{_mv(p['extras'].get('gnd_die_pp'))} mV",
        )
    )
    a("")
    a(
        "Peak-to-peak `GND_DIE` excursion over the same steady-state conversion "
        "the fragment averages its supply currents over. The "
        f"`{CONTROL_ARM}` control's own value is "
        f"{'n/a' if control is None else _mv(control['extras'].get('gnd_die_pp'))} mV "
        "-- mechanically zero, because an ideal source holds the die node at 0 V; a "
        "nonzero value there would mean the networks are not wired as stated."
    )
    a("")

    a("## Worst mid-scale |delta code| vs the control, over the swept box")
    a("")
    lines.extend(
        sweep_matrix_lines(
            points,
            l_mults,
            rsubx_values,
            lambda p: (
                "n/a"
                if control is None or worst_mid_scale_delta(p, control) is None
                else f"{worst_mid_scale_delta(p, control)} LSB"
            ),
        )
    )
    a("")
    a(
        "The two `+-0.78*V_REF` inputs are EXCLUDED from this matrix (they are "
        "reported per point in the table below): "
        "`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` already "
        "records them as wrong by ~100 LSB at every corner (issue #267, "
        "common-mode saturation at large differential input, still open), so a "
        "change there could not be attributed to supply impedance."
    )
    a("")

    a("## Captured code per point")
    a("")
    a(
        "| point | "
        + " | ".join(f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)})" for f in tb.INPUT_FRACTIONS)
        + " | worst \\|delta code\\| vs `ideal` (mid-scale) |"
    )
    a("|---" * (len(tb.INPUT_FRACTIONS) + 2) + "|")
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
        a(f"| `{p['arm']}` | " + " | ".join(cells) + f" | {worst} |")
    a("")

    a("## Rail excursion and average current per point")
    a("")
    a(
        "| point | "
        + " | ".join(f"{name} pp (mV)" for name, _n, _l in RAIL_PROBES)
        + " | I(VDD) (uA) | I(VPWR) (uA) | I(GND) (uA) | total power (uW) |"
    )
    a("|---" * (len(RAIL_PROBES) + 5) + "|")
    for p in points:
        cells = [_mv(p["extras"].get(f"{probe}_pp")) for probe, _n, _l in RAIL_PROBES]
        i_gnda = p["extras"].get("i_gnda")
        a(
            f"| `{p['arm']}` | "
            + " | ".join(cells)
            + f" | {_ua(p['currents'].get('i_vdd'))} | {_ua(p['currents'].get('i_vpwr'))} | "
            + f"{'n/a (no bond)' if i_gnda is None else _ua(abs(i_gnda))} | "
            + f"{p['power_w'] * 1e6:.3f} |"
        )
    a("")

    a("## Findings")
    a("")
    for line in sweep_findings_lines(points, control, l_mults, rsubx_values):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    a("| point | wall clock (s) | x the `ideal` control |")
    a("|---|---|---|")
    base = None if control is None else control.get("wall_s")
    for p in points:
        ratio = "--" if not base else f"{p['wall_s'] / base:.2f}x"
        note = " (log reused from cache)" if p.get("reused") else ""
        a(f"| `{p['arm']}` | {p['wall_s']:.0f}{note} | {ratio} |")
    a("")
    if any(p.get("reused") for p in points):
        a(
            "Rows marked **log reused from cache** were not re-simulated for this "
            "record: `--log-cache` found a stored ngspice log whose deck sha256, "
            "volare-verified open_pdks commit and ngspice version all matched the "
            "run about to be made, and reused it rather than repeating a "
            "tens-of-minutes transient after an interruption. The reported wall "
            "clock is the one measured when that run actually executed. A mismatch "
            "on any identity field re-simulates, and a host that cannot verify its "
            "own open_pdks commit or ngspice version never reuses at all."
        )
        a("")
    a(
        "Reported for the same two reasons the arm-comparison record reports it: it "
        "is the input to the subset-corner justification below, and the cost itself "
        "tracks the physics -- an undecoupled series inductance against the die's "
        "own capacitance rings above the clock rate and forces the transient "
        "solver's timestep down. These are wall-clock seconds on a shared, "
        "contended host, so they are ratios between points rather than a benchmark."
    )
    a("")

    a("## What this sweep does not cover")
    a("")
    a(
        "Stated for the same reason `sim/README.md` requires a corner subset to be "
        "justified: a reader must not have to infer which questions this box leaves "
        "open."
    )
    a("")
    a(
        "- **The substrate-only RETURN is not swept here.** On the as-built "
        f"`{SWEEP_BASE_ARM}` topology this grid moves around, `GND` has a bond of "
        "its own, so the swept resistor is a shunt between two ground die nodes "
        "rather than the analog ground's path to the board. The topology where the "
        "same element IS that path is `no-gnd-pad` (DR-012's rejected null "
        "option); sweeping it there is a separate ladder with a separate reading, "
        f"which this runner provides as `--null-sweep`."
    )
    a(
        "- **No extracted substrate network.** `R_SUBX` remains a single lumped "
        "resistor standing in for a distributed, layout-dependent network, with no "
        "`klt extract` behind it (issue #409's fourth item). Sweeping a stand-in "
        "over two decades bounds the *sensitivity* to it; it does not turn it into "
        "a measurement of this die."
    )
    a(
        "- **No BOARD decoupling** is modelled anywhere in this campaign. On-die "
        "decoupling is whatever the committed `design/sar_adc_top.spice` carries: "
        "since DR-016 (issue #431) that is one `cap_mim_m3_1` per supply domain, "
        "and DR-015 item 6's `no decoupling is modelled' premise no longer holds. "
        "Read a record's own DUT netlist sha256 to know which case it is."
    )
    a(
        "- **The two near-full-scale inputs** are outside every code comparison "
        "above, for the reason stated under the delta matrix (issue #267)."
    )
    a(
        "- **The box is bounded, and a null inside it is not a null outside it.** "
        f"`L` is swept to {max(l_mults):g}x DR-015's value and `R_SUBX` over "
        f"{min(rsubx_values):g}-{max(rsubx_values):g} Ohm at one corner. Nothing "
        "here states what happens beyond those edges."
    )
    a("")

    lines.extend(
        subset_corner_lines(
            corner_ids,
            "the sweep",
            f"the {len(points)} decks of this record",
            len(points),
            "a bounded sensitivity map at the baseline corner",
        )
    )

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per run",
                "runs": (
                    f"{len(points)} ({len(grid_points)} swept points + the "
                    f"`{CONTROL_ARM}` control x {len(corner_ids)} corner point)"
                ),
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "swept box": (
                    "bond L in {"
                    + ", ".join(f"{m:g}x" for m in l_mults)
                    + "} of DR-015's "
                    + f"{PACKAGE_L_H * 1e9:.3f} nH; R_SUBX in "
                    + "{"
                    + ", ".join(f"{r:g}" for r in rsubx_values)
                    + "} Ohm; bond R fixed at "
                    + f"{PACKAGE_R_OHM * 1e3:.1f} mOhm (DR-015)"
                ),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            sweep_invocation_line(l_mults, rsubx_values, supersedes), supersedes
        )
    )

    # Deliberately NOT records/LATEST. That pointer names the record this
    # campaign's cited claim rests on -- the arm comparison DR-012 and
    # `docs/chipalooza/challenge-4-proposal.md`'s Power row cite by id -- and
    # this record does not replace it: it is a distinct, non-superseding claim
    # about a different question (how far the answer moves around DR-015's
    # assumption point). Moving the pointer would make a citation of the
    # still-current arm-comparison record read as stale to the citation gate
    # while nothing had actually superseded it. Same disposition, for the same
    # reason, as `sim/full-conversion-transient/run_conversion.py`'s diagnostic
    # record writers.
    return evidence.close_record(prov, lines, "Sweep record")


# --------------------------------------------------------------------------
# The null-option sweep's own record
# --------------------------------------------------------------------------
def null_sweep_invocation_line(rsubx_values: tuple[float, ...], supersedes: str) -> str:
    """The `--null-sweep` counterpart of `invocation_line()`, under the same
    rules: a flag that changes what was simulated is stated, one that only
    changes how the run was scheduled (`--log-cache`) is not. The axis flag
    appears only when the run departed from the documented ladder, so the
    default run's footer is exactly the command `sim/spec-coverage.json`
    indexes."""
    parts = [RUNNER_REL, "--null-sweep"]
    if tuple(rsubx_values) != NULL_SWEEP_RSUBX_OHM:
        parts.append("--null-sweep-rsub " + ",".join(f"{r:g}" for r in rsubx_values))
    parts.append("--record")
    if supersedes:
        parts.append(f"--supersedes {supersedes}")
    return " ".join(parts)


def _null_sweep_point(points: list[dict], rsubx_ohm: float) -> dict | None:
    name = null_sweep_arm_name(rsubx_ohm)
    return next((p for p in points if p["arm"] == name), None)


def null_sweep_findings_lines(
    points: list[dict], control: dict | None, rsubx_values: tuple[float, ...]
) -> list[str]:
    """What the null-option ladder says.

    Every bullet is about a MAGNITUDE, because the gap this closes is a
    magnitude claim: DR-015 asserts that the rejected topology looks harmless
    at a small substrate resistance and fatal at a large one, from a single
    measured point. The bullets below either find that transition inside the
    ladder or report that it is not there -- and say which.
    """
    out: list[str] = []

    out.append(
        "- **The ladder is anchored to the committed ground-pad ablation.** Its "
        f"`{null_sweep_arm_name(R_SUBX_OHM)}` point is, card for card, the "
        f"`{NULL_SWEEP_BASE_ARM}` arm this campaign already recorded at this corner: "
        "same three bonded terminals at DR-015's R+L, same unbonded `GND`, same "
        "stimulus, same lumped resistor at DR-015's assumed "
        f"{R_SUBX_OHM:g} Ohm. "
        + (
            "Checked at record-write time (`null_sweep_anchor_matches_base_arm()`), "
            "so the ladder is tied to that record rather than merely described as "
            "being."
            if null_sweep_anchor_matches_base_arm()
            else "**This check FAILED at record-write time** -- the anchor point is no "
            "longer the committed null-option arm, so nothing below may be read as a "
            "walk away from DR-015's assumption point."
        )
    )

    cells = []
    for r in rsubx_values:
        p = _null_sweep_point(points, r)
        pp = None if p is None else p["extras"].get("gnd_die_pp")
        cells.append("n/a" if pp is None else f"{pp * 1e3:.3f} mV")
    out.append(
        "- **Die-side analog-ground excursion along the ladder**: "
        + " -> ".join(cells)
        + " as the lumped substrate return goes "
        + " -> ".join(f"{r:g} Ohm" for r in rsubx_values)
        + ". Only that resistor moves, so the change is the substrate return's own "
        "contribution and nothing else (DR-015 item 5)."
    )

    if control is not None:
        moved = []
        for r in rsubx_values:
            p = _null_sweep_point(points, r)
            if p is None:
                continue
            delta = worst_mid_scale_delta(p, control)
            if delta:
                moved.append((r, delta))
        if moved:
            first = min(moved, key=lambda t: t[0])
            out.append(
                "- **A mid-scale captured code moves inside this ladder.** The "
                f"smallest substrate resistance at which it does is "
                f"**{first[0]:g} Ohm** (worst mid-scale |delta code| = "
                f"**{first[1]} LSB** vs the `{CONTROL_ARM}` control); "
                f"{len(moved)} of {len(rsubx_values)} points move at least one "
                "mid-scale code. So DR-012's rejected topology has a substrate "
                "magnitude at which it stops being free, that magnitude is located "
                "**inside** the swept ladder at this corner, and DR-015's assumed "
                f"{R_SUBX_OHM:g} Ohm is on one side of it."
            )
        else:
            out.append(
                "- **No mid-scale captured code moves anywhere in this ladder.** "
                f"Every point reproduces the `{CONTROL_ARM}` control's mid-scale "
                "codes exactly (worst |delta code| = **0 LSB**) across "
                f"{min(rsubx_values):g}-{max(rsubx_values):g} Ohm of lumped substrate "
                "return. That is a **bounded null result** for DR-012's rejected "
                "option: the magnitude at which deleting the analog ground pad "
                "would cost a code is **outside** this ladder, not located inside "
                "it, and a wider ladder (or another corner) could still find one. "
                "It is specifically NOT a finding that the pad does not matter -- "
                "the excursion row above moves even where the code row does not."
            )

    worst = None
    for r in rsubx_values:
        p = _null_sweep_point(points, r)
        pp = None if p is None else p["extras"].get("gnd_die_pp")
        if pp is not None and (worst is None or pp > worst[1]):
            worst = (r, pp)
    if worst is not None:
        lsb_v = 2.0 * NOMINAL_SUPPLY_V / 2**tb.N_BITS
        out.append(
            "- **Worst die-side analog-ground excursion on the ladder**: "
            f"**{worst[1] * 1e3:.3f} mV** peak-to-peak ({worst[1] / lsb_v:.3f} LSB at "
            f"the nominal supply) at a {worst[0]:g} Ohm substrate return. "
            "Undecoupled by construction (DR-015 item 6): this design has no on-die "
            "decoupling and none is modelled, so the figure is an upper bound rather "
            "than a prediction."
        )

    # The sensitivity itself -- the number DR-015's prose asserted and nothing
    # measured. Reported as a ratio across the whole ladder rather than a slope,
    # because two decades of a lumped stand-in is not a curve anyone should fit.
    first_p = _null_sweep_point(points, min(rsubx_values))
    last_p = _null_sweep_point(points, max(rsubx_values))
    pp_first = None if first_p is None else first_p["extras"].get("gnd_die_pp")
    pp_last = None if last_p is None else last_p["extras"].get("gnd_die_pp")
    if pp_first and pp_last:
        out.append(
            "- **How sensitive the rejected option actually is to the assumption**: "
            f"a {max(rsubx_values) / min(rsubx_values):g}x change in the lumped "
            "substrate return (from "
            f"{min(rsubx_values):g} to {max(rsubx_values):g} Ohm) moves the die-side "
            f"analog-ground excursion by {pp_last / pp_first:.2f}x "
            f"({pp_first * 1e3:.3f} mV -> {pp_last * 1e3:.3f} mV). This is the "
            "measured version of DR-015's own prose claim that the arm is "
            "\"*entirely* a function of `R_SUB`\" -- which was, until this record, an "
            "argument from one point."
        )

    missing_points = [p["point_id"] for p in points if p["missing"]]
    if missing_points:
        out.append(
            "- **Incomplete runs** (some `.meas` value did not come back): "
            + ", ".join(f"`{pid}`" for pid in missing_points)
            + " -- reported rather than dropped."
        )
    return out


def write_null_sweep_record(
    points: list[dict],
    dut_netlist_text: str,
    rsubx_values: tuple[float, ...],
    supersedes: str = "",
) -> Path:
    """The `--null-sweep` record.

    A third writer, for the same reason there is a second: these records make
    different claims and must not be able to borrow each other's sentences.
    `write_record()` compares NETWORKS at DR-015's assumption point;
    `write_sweep_record()` walks a 2-D box around that point on the AS-BUILT
    network; this one walks one axis on the REJECTED network, where that axis
    is the entire ground return rather than a shunt. The shared parts -- the
    DR-015 assumption table, the subset-corner justification, the environment
    block, the footer rules -- are shared by calling the same helpers, so none
    of the three can drift into a softer version of another's caveats.
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

    swept = [p for p in points if p["arm"] != CONTROL_ARM]
    corner_ids = sorted({p["corner_id"] for p in points})
    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})
    control = next((p for p in points if p["arm"] == CONTROL_ARM), None)

    a = lines.append
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- **Power** (DRAFT row), "
        "INFORMATIONAL only, and the evidence "
        "`spec/decision-records/DR-015-package-parasitic-assumption.md` needs to "
        "support a sensitivity claim it currently makes in prose: that the "
        f"`{NULL_SWEEP_BASE_ARM}` arm -- DR-012's REJECTED null option -- is "
        "\"*entirely* a function of `R_SUB`: with a small `R_SUB` it looks harmless, "
        "with a large one it looks fatal\". It edits no spec row, proposes no power "
        "target, and grades nothing against a ratified line."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with two "
        "TESTBENCH-ONLY transformations that are never written back to `design/`: "
        "the DUT's `GND` net is renamed `GND_DIE` (a net named `GND` is ngspice's "
        "global node 0 and would short out every series element this campaign "
        "inserts), and the committed fragment's `VVDD`/`VVPWR`/`VVGND` source "
        "cards are re-pointed to board-side nodes. Source instance names, the "
        "`.tran` card, the clock/reset/input schedule and every code and phase "
        "`.meas` card are used verbatim."
    )
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Ladder**: {len(swept)} substrate-return resistances plus the "
        f"`{CONTROL_ARM}` control, at {len(corner_ids)} corner point(s) = "
        f"{len(points)} whole-ADC transients. Every swept point is the "
        f"`{NULL_SWEEP_BASE_ARM}` topology (`GND` unbonded; `VDD`/`VPWR`/`VGND` at "
        "DR-015's R+L) with exactly one element moved."
    )
    a(
        "- **Stimulus**: `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice`, unmodified except for the supply "
        f"source cards' nodes -- `f_clk = {tb.F_CLK_HZ / 1e6:g} MHz` (DR-006 worst "
        f"case), {tb.N_CONVERSIONS} back-to-back conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods, the first discarded as start-up, "
        "the remaining five carrying DC differential inputs of "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + "."
    )
    a("")

    a("## Why this record exists")
    a("")
    a(
        "[DR-015](../../../spec/decision-records/DR-015-package-parasitic-assumption.md)'s "
        "Consequences section says, of the arm that implements DR-012's *rejected* "
        f"option: \"The `{NULL_SWEEP_BASE_ARM}` arm ... is **entirely** a function of "
        "`R_SUB`: with a small `R_SUB` it looks harmless, with a large one it looks "
        "fatal.\" Until this record that was an argument, not a measurement -- the "
        "campaign had run that topology at exactly one substrate magnitude "
        f"({R_SUBX_OHM:g} Ohm), so \"harmless\" and \"fatal\" were both extrapolations "
        "from a single point. This record is the bounded ladder that turns the "
        "sensitivity into a number, at the baseline corner, and it is the residual "
        "of [issue #409](https://github.com/2AMLogic/sky130-sar-adc/issues/409)'s "
        "third item that the 2-D box did not reach."
    )
    a("")
    a(
        "**It supersedes nothing, and is not a re-run of the 2-D sweep.** That box "
        f"moved a substrate resistance on the as-built `{SWEEP_BASE_ARM}` topology, "
        "where `GND` is bonded through ~"
        f"{PACKAGE_R_OHM * 1e3:.0f} mOhm and the substrate resistor is a secondary "
        "shunt between two ground die nodes. Here the SAME element carries the "
        "analog ground's entire return current, because there is no analog ground "
        "bond at all. Same constant, same decade, structurally different "
        "experiment -- and the reason the earlier record's own scope section said "
        "an `R_SUB` sweep was still owed."
    )
    a("")

    a("## Which stand-in this ladder moves, and what it is called")
    a("")
    a(
        "DR-015 item 2 defines two lumped stand-ins: `R_SUB`, a substrate-only "
        "ground RETURN, and `R_SUBX`, the link \"between the analog and digital "
        f"ground die nodes\". In the `{NULL_SWEEP_BASE_ARM}` topology **one resistor "
        "is both**: it spans `GND_DIE` and `VGND` (so the deck names its instance "
        "`RSUBX`, after the node pair it bridges) and, with `GND` unbonded, it is "
        "also the only path the analog ground has to the board (so it plays "
        "`R_SUB`'s role). DR-015 sets both stand-ins to the same "
        f"{R_SUBX_OHM:g} Ohm, so at the anchor point the distinction changes no "
        "number -- but a record that swept \"the substrate resistance\" without "
        "saying which element moved would be unreadable against the 2-D box, which "
        "swept an element with the same name in a topology where it does something "
        "else. What moved here is the single resistor named in every deck under "
        "this record, and nothing else."
    )
    a("")

    a("## The package-style assumption (DR-015), and which of it is swept")
    a("")
    lines.extend(_assumption_lines())
    a("")
    a(
        "The ladder moves **only** the lumped substrate row. The per-terminal bond "
        f"R+L is held at DR-015's stated {PACKAGE_R_OHM * 1e3:.1f} mOhm / "
        f"{PACKAGE_L_H * 1e9:.3f} nH on all three bonded terminals throughout, so "
        "each step changes one element and nothing else (DR-015 item 5)."
    )
    a("")

    a("## The swept points, as networks")
    a("")
    lines.extend(
        arm_table_lines(
            [ARMS_BY_NAME[CONTROL_ARM]] + [null_sweep_arm(r) for r in rsubx_values],
            substrate_note=False,
        )
    )
    a(
        f"The `{CONTROL_ARM}` row is the control every delta below is taken against: "
        "ideal sources at the die, the zero-impedance case every other `sim/` "
        "campaign runs. Each swept row carries its own lumped resistor between the "
        "analog and digital ground DIE nodes, which is the swept axis; in `ideal` "
        "both ends of that resistor are held at 0 V, so it carries no current and "
        "the control stays a true zero-impedance reference."
    )
    a("")

    a("## Die-side analog-ground excursion along the ladder")
    a("")
    a(
        "| lumped substrate return | `GND_DIE` pp | `VGND` pp | worst mid-scale "
        "\\|delta code\\| vs `ideal` |"
    )
    a("|---|---|---|---|")
    for r in rsubx_values:
        p = _null_sweep_point(points, r)
        if p is None:
            a(f"| **{r:g} Ohm** | (not run) | (not run) | (not run) |")
            continue
        worst = (
            "n/a"
            if control is None or worst_mid_scale_delta(p, control) is None
            else f"{worst_mid_scale_delta(p, control)} LSB"
        )
        anchor = " (anchor)" if r == R_SUBX_OHM else ""
        a(
            f"| **{r:g} Ohm**{anchor} | {_mv(p['extras'].get('gnd_die_pp'))} mV | "
            f"{_mv(p['extras'].get('vgnd_die_pp'))} mV | {worst} |"
        )
    a("")
    a(
        "Peak-to-peak over the same steady-state conversion the fragment averages "
        f"its supply currents over. The `{CONTROL_ARM}` control's own `GND_DIE` "
        "value is "
        f"{'n/a' if control is None else _mv(control['extras'].get('gnd_die_pp'))} mV "
        "-- mechanically zero, because an ideal source holds the die node at 0 V; a "
        "nonzero value there would mean the networks are not wired as stated. The "
        "two `+-0.78*V_REF` inputs are EXCLUDED from the delta column (they are "
        "reported per point in the table below): "
        "`sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` already "
        "records them as wrong by ~100 LSB at every corner (issue #267, "
        "common-mode saturation at large differential input, still open), so a "
        "change there could not be attributed to supply impedance."
    )
    a("")

    a("## Captured code per point")
    a("")
    a(
        "| point | "
        + " | ".join(f"`{f:+.2f}*V_REF` (ideal {tb.ideal_code(f)})" for f in tb.INPUT_FRACTIONS)
        + " | worst \\|delta code\\| vs `ideal` (mid-scale) |"
    )
    a("|---" * (len(tb.INPUT_FRACTIONS) + 2) + "|")
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
        a(f"| `{p['arm']}` | " + " | ".join(cells) + f" | {worst} |")
    a("")

    a("## Rail excursion and average current per point")
    a("")
    a(
        "| point | "
        + " | ".join(f"{name} pp (mV)" for name, _n, _l in RAIL_PROBES)
        + " | I(VDD) (uA) | I(VPWR) (uA) | I(GND) (uA) | total power (uW) |"
    )
    a("|---" * (len(RAIL_PROBES) + 5) + "|")
    for p in points:
        cells = [_mv(p["extras"].get(f"{probe}_pp")) for probe, _n, _l in RAIL_PROBES]
        i_gnda = p["extras"].get("i_gnda")
        a(
            f"| `{p['arm']}` | "
            + " | ".join(cells)
            + f" | {_ua(p['currents'].get('i_vdd'))} | {_ua(p['currents'].get('i_vpwr'))} | "
            + f"{'n/a (no bond)' if i_gnda is None else _ua(abs(i_gnda))} | "
            + f"{p['power_w'] * 1e6:.3f} |"
        )
    a("")
    a(
        "`I(GND)` is `n/a (no bond)` on every swept row by construction: this "
        "topology's whole point is that the analog ground has no bond current to "
        "measure, because it has no bond."
    )
    a("")

    a("## Findings")
    a("")
    for line in null_sweep_findings_lines(points, control, rsubx_values):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    a("| point | wall clock (s) | x the `ideal` control |")
    a("|---|---|---|")
    base = None if control is None else control.get("wall_s")
    for p in points:
        ratio = "--" if not base else f"{p['wall_s'] / base:.2f}x"
        note = " (log reused from cache)" if p.get("reused") else ""
        a(f"| `{p['arm']}` | {p['wall_s']:.0f}{note} | {ratio} |")
    a("")
    if any(p.get("reused") for p in points):
        a(
            "Rows marked **log reused from cache** were not re-simulated for this "
            "record: `--log-cache` found a stored ngspice log whose deck sha256, "
            "volare-verified open_pdks commit and ngspice version all matched the "
            "run about to be made, and reused it rather than repeating a "
            "tens-of-minutes transient after an interruption. The reported wall "
            "clock is the one measured when that run actually executed. A mismatch "
            "on any identity field re-simulates, and a host that cannot verify its "
            "own open_pdks commit or ngspice version never reuses at all."
        )
        a("")
    a(
        "Reported because this campaign's cost history is itself evidence: this "
        "topology was left unrun across several passes on a truncated-slice "
        "projection of roughly an order of magnitude that a full run then "
        "falsified (1.67x the control, "
        "`records/20260925-204633-7339971.md`). These are wall-clock seconds on a "
        "shared, contended host, so they are ratios between points rather than a "
        "benchmark."
    )
    a("")

    a("## What this ladder does not cover")
    a("")
    a(
        "Stated for the same reason `sim/README.md` requires a corner subset to be "
        "justified: a reader must not have to infer which questions it leaves open."
    )
    a("")
    a(
        "- **No extracted substrate network** (issue #409's fourth item, and "
        "DR-015's own still-open one). The swept element is a single lumped "
        "resistor standing in for a distributed, layout-dependent thing, with no "
        "`klt extract` behind it. Sweeping a stand-in over two decades bounds the "
        "*sensitivity* to it -- which is exactly what this record is for -- but it "
        "does not turn any point of the ladder into a measurement of this die's "
        "substrate, and no number here may be quoted as one."
    )
    a(
        "- **The bond inductance is not crossed with this axis.** All three bonded "
        "terminals stay at DR-015's R+L throughout, so this is a one-axis ladder "
        "and not a second 2-D box. A point here is therefore a statement about the "
        "substrate return at DR-015's bond, not at an arbitrary one."
    )
    a(
        "- **No decoupling, on-die or on-board** (DR-015 item 6, carried from "
        "DR-010 and DR-012). Every point here is the undecoupled case."
    )
    a(
        "- **The two near-full-scale inputs** are outside every code comparison "
        "above, for the reason stated under the excursion table (issue #267)."
    )
    a(
        "- **The ladder is bounded, and a null inside it is not a null outside "
        f"it.** The substrate return is swept over {min(rsubx_values):g}-"
        f"{max(rsubx_values):g} Ohm at one corner. Nothing here states what happens "
        "beyond those edges."
    )
    a("")

    lines.extend(
        subset_corner_lines(
            corner_ids,
            "the null-option substrate ladder",
            f"the {len(points)} decks of this record",
            len(points),
            "a bounded sensitivity ladder at the baseline corner",
        )
    )

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per run",
                "runs": (
                    f"{len(points)} ({len(swept)} swept points + the "
                    f"`{CONTROL_ARM}` control x {len(corner_ids)} corner point)"
                ),
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "swept ladder": (
                    f"`{NULL_SWEEP_BASE_ARM}` topology; lumped substrate return in {{"
                    + ", ".join(f"{r:g}" for r in rsubx_values)
                    + "} Ohm (DR-015 assumes "
                    + f"{R_SUBX_OHM:g}); bond R+L fixed at {PACKAGE_R_OHM * 1e3:.1f} "
                    + f"mOhm / {PACKAGE_L_H * 1e9:.3f} nH on VDD/VPWR/VGND (DR-015)"
                ),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            null_sweep_invocation_line(rsubx_values, supersedes), supersedes
        )
    )

    # Deliberately NOT records/LATEST, for the same reason the 2-D sweep record
    # is not: that pointer names this flow's newest ARM-COMPARISON record, which
    # is what `check_proposal_citations.py`'s arm census reads. This record
    # contains no arm census to offer -- it is one topology at three magnitudes
    # -- and moving the pointer onto it would make a citation of a record
    # nothing had superseded read as stale.
    return evidence.close_record(prov, lines, "Null-option sweep record")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin")
    ap.add_argument(
        "--corners",
        action="store_true",
        help="run every arm at all nine points of the ratified OAT grid instead of "
        "the baseline corner only (NOT runnable on a shared dispatch host -- see "
        "this experiment's README.md)",
    )
    ap.add_argument(
        "--arms",
        default=None,
        help="comma-separated subset of the supply-return arms to run (default: all). "
        "Not meaningful with --sweep, which synthesizes its own grid points.",
    )
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="DR-015's own open item (issue #409): instead of the named arms, run a "
        "bounded 2-D sweep of the AS-BUILT supply-return network at the baseline "
        "corner -- per-terminal bond inductance (as a multiple of DR-015's value) x "
        "the lumped substrate link R_SUBX -- plus the `ideal` control. Writes its "
        "own record with --record; that record does NOT supersede the arm-comparison "
        "record and does not move records/LATEST.",
    )
    ap.add_argument(
        "--sweep-l-mult",
        default=",".join(f"{m:g}" for m in SWEEP_L_MULTIPLIERS),
        metavar="M1,M2,...",
        help="the sweep's bond-inductance axis, as multipliers of DR-015's "
        f"per-terminal {PACKAGE_L_H * 1e9:.3f} nH (default: "
        f"{','.join(f'{m:g}' for m in SWEEP_L_MULTIPLIERS)}). A departure from the "
        "default box is stated in the record's own footer.",
    )
    ap.add_argument(
        "--sweep-rsubx",
        default=",".join(f"{r:g}" for r in SWEEP_RSUBX_OHM),
        metavar="R1,R2,...",
        help="the sweep's substrate-link axis, in ohms (default: "
        f"{','.join(f'{r:g}' for r in SWEEP_RSUBX_OHM)}; DR-015 assumes "
        f"{R_SUBX_OHM:g}). This is R_SUBX, the lumped GND/VGND substrate link -- "
        "NOT R_SUB, which the as-built network does not contain.",
    )
    ap.add_argument(
        "--null-sweep",
        action="store_true",
        help="the residual of DR-015's substrate open item (issue #409): instead of "
        "the named arms, run a bounded ONE-axis ladder over the lumped substrate "
        f"return of the `{NULL_SWEEP_BASE_ARM}` topology -- DR-012's rejected null "
        "option, where that one resistor is the analog ground's entire path to the "
        "board -- at the baseline corner, plus the `ideal` control. Not the same "
        f"experiment as --sweep, which moves the same constant on the as-built "
        f"`{SWEEP_BASE_ARM}` topology where `GND` is bonded. Writes its own record "
        "with --record; that record supersedes nothing and does not move "
        "records/LATEST.",
    )
    ap.add_argument(
        "--null-sweep-rsub",
        default=",".join(f"{r:g}" for r in NULL_SWEEP_RSUBX_OHM),
        metavar="R1,R2,...",
        help="the null-option ladder's substrate axis, in ohms (default: "
        f"{','.join(f'{r:g}' for r in NULL_SWEEP_RSUBX_OHM)}; DR-015 assumes "
        f"{R_SUBX_OHM:g}). A departure from the default ladder is stated in the "
        "record's own footer.",
    )
    ap.add_argument(
        "--cost-probe",
        type=float,
        default=None,
        metavar="NS",
        help="price the --sweep box instead of measuring it: re-run each grid "
        "point's own deck over a TRUNCATED transient of NS nanoseconds and report "
        "only wall clock and whether the solver converged. Measures nothing about "
        "the DUT (the fragment's .meas cards sit outside the sliced span), so it "
        "refuses --record and --log-cache; it exists so the box's price and "
        "runnability are known before the hours are spent on it.",
    )
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--log-cache",
        default="",
        metavar="DIR",
        help="cache each completed run's ngspice log in DIR and reuse a cached log "
        "when its deck sha256, volare-verified open_pdks commit and ngspice version "
        "all match the run about to be made. One arm here is a tens-of-minutes "
        "whole-ADC transient and five in sequence outlive most process supervisors, "
        "so this makes an interrupted campaign restartable without re-simulating "
        "the arms that already finished. A mismatch on any identity field "
        "re-simulates, and a host that cannot verify its own open_pdks commit or "
        "ngspice version neither stores nor reuses; the record names which of its "
        "runs were reused.",
    )
    ap.add_argument(
        "--supersedes",
        default="",
        metavar="RECORD_ID",
        help="record-id of the prior record of THIS experiment that the new record "
        "replaces for the same claim (sim/README.md's append-only convention)",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    arm_names = [
        name.strip()
        for name in (args.arms or ",".join(arm.name for arm in ARMS)).split(",")
        if name.strip()
    ]
    unknown = [name for name in arm_names if name not in ARMS_BY_NAME]
    if unknown:
        print(
            f"FAIL: unknown arm(s) {unknown} -- available: "
            f"{[arm.name for arm in ARMS]}",
            file=sys.stderr,
        )
        return 2
    if CONTROL_ARM not in arm_names:
        print(
            f"FAIL: the `{CONTROL_ARM}` control arm must be included -- every number "
            "this campaign reports is a difference against it.",
            file=sys.stderr,
        )
        return 2

    l_mults: tuple[float, ...] = ()
    rsubx_values: tuple[float, ...] = ()
    null_rsub_values: tuple[float, ...] = ()
    if args.sweep and args.null_sweep:
        print(
            "FAIL: --sweep and --null-sweep are different experiments on different "
            f"topologies (the as-built `{SWEEP_BASE_ARM}` network and DR-012's "
            f"rejected `{NULL_SWEEP_BASE_ARM}` one) and each writes its own record. "
            "Run them one at a time.",
            file=sys.stderr,
        )
        return 2
    if args.null_sweep:
        if args.arms is not None:
            print(
                "FAIL: --arms is not meaningful with --null-sweep. The ladder "
                f"synthesizes its own points over the `{NULL_SWEEP_BASE_ARM}` "
                f"topology and always runs the `{CONTROL_ARM}` control; pick the "
                "ladder with --null-sweep-rsub instead.",
                file=sys.stderr,
            )
            return 2
        if args.corners:
            print(
                "FAIL: --null-sweep --corners is refused, for the same reason "
                "--sweep --corners is: it multiplies a swept ladder by the ratified "
                "grid, and this host may not run a multi-corner ngspice grid at all "
                "-- see this experiment's README.md.",
                file=sys.stderr,
            )
            return 2
        try:
            null_rsub_values = tuple(
                float(v) for v in args.null_sweep_rsub.split(",") if v.strip()
            )
        except ValueError as exc:
            print(f"FAIL: could not parse the null-sweep axis: {exc}", file=sys.stderr)
            return 2
        if not null_rsub_values:
            print("FAIL: the null-sweep axis needs at least one value", file=sys.stderr)
            return 2
        try:
            null_sweep_arms(null_rsub_values)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        if not null_sweep_anchor_matches_base_arm():
            print(
                f"FAIL: the null sweep's anchor point (R = {R_SUBX_OHM:g} Ohm) is no "
                f"longer card-for-card the `{NULL_SWEEP_BASE_ARM}` arm -- the ladder "
                "would not be a walk away from DR-015's assumption point. Re-derive "
                "it before running.",
                file=sys.stderr,
            )
            return 2
    if args.sweep:
        if args.arms is not None:
            print(
                "FAIL: --arms is not meaningful with --sweep. The sweep synthesizes "
                f"its own grid points over the as-built `{SWEEP_BASE_ARM}` topology "
                f"and always runs the `{CONTROL_ARM}` control; pick the box with "
                "--sweep-l-mult / --sweep-rsubx instead.",
                file=sys.stderr,
            )
            return 2
        if args.corners:
            print(
                "FAIL: --sweep --corners is refused. It is the two deferred costs of "
                "issue #409 multiplied together (a 2-D box at every ratified corner), "
                "and this host may not run a multi-corner ngspice grid at all -- see "
                "this experiment's README.md.",
                file=sys.stderr,
            )
            return 2
        try:
            l_mults = tuple(float(v) for v in args.sweep_l_mult.split(",") if v.strip())
            rsubx_values = tuple(float(v) for v in args.sweep_rsubx.split(",") if v.strip())
        except ValueError as exc:
            print(f"FAIL: could not parse a sweep axis: {exc}", file=sys.stderr)
            return 2
        if not l_mults or not rsubx_values:
            print("FAIL: both sweep axes need at least one value", file=sys.stderr)
            return 2
        try:
            sweep_arms(l_mults, rsubx_values)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        if not sweep_anchor_matches_base_arm():
            print(
                "FAIL: the sweep's anchor point (1x DR-015's L, "
                f"R_SUBX = {R_SUBX_OHM:g} Ohm) is no longer card-for-card the "
                f"`{SWEEP_BASE_ARM}` arm -- the sweep would not be a walk around the "
                "campaign's own assumption point. Re-derive it before running.",
                file=sys.stderr,
            )
            return 2

    if args.cost_probe is not None:
        if not (args.sweep or args.null_sweep):
            print(
                "FAIL: --cost-probe prices a synthesized box or ladder; pass "
                "--sweep or --null-sweep too. The named arms already have measured "
                "per-run wall clock in the campaign's arm-comparison records.",
                file=sys.stderr,
            )
            return 2
        if args.record:
            print(
                "FAIL: --cost-probe --record is refused. A truncated transient "
                "measures nothing about this DUT -- the stimulus fragment's .meas "
                "cards sit at conversion times outside the sliced span -- so no "
                "record may be minted from one.",
                file=sys.stderr,
            )
            return 2
        if args.log_cache:
            print(
                "FAIL: --cost-probe --log-cache is refused. A probe's log is keyed "
                "by the same point-id as the real run of that point, so caching one "
                "would overwrite the stored log the real campaign restarts from. A "
                "probe is minutes; it does not need to be restartable.",
                file=sys.stderr,
            )
            return 2
        if args.supersedes:
            print(
                "FAIL: --cost-probe --supersedes is refused: a probe writes no "
                "record, so it can supersede nothing.",
                file=sys.stderr,
            )
            return 2
        if args.cost_probe <= 0.0:
            print("FAIL: --cost-probe takes a positive number of nanoseconds", file=sys.stderr)
            return 2
        stimulus_ns = fragment_tran_stop_ns()
        if stimulus_ns is not None and args.cost_probe >= stimulus_ns:
            print(
                f"FAIL: a {args.cost_probe:g} ns probe is not shorter than the "
                f"{stimulus_ns:g} ns stimulus it exists to price -- run the campaign "
                "itself instead of probing it.",
                file=sys.stderr,
            )
            return 2

    if args.supersedes and not (
        EXPERIMENT_DIR / "records" / f"{args.supersedes}.md"
    ).is_file():
        print(
            f"FAIL: --supersedes {args.supersedes}: no such record under "
            f"{os.path.relpath(EXPERIMENT_DIR / 'records', REPO_ROOT)}/",
            file=sys.stderr,
        )
        return 2

    check = toolchain.check_env()
    if args.check_env:
        print(toolchain.summary())
        for m in check.messages:
            print(f"FAIL: {m}")
        for w in check.warnings:
            print(f"WARNING: {w}")
        return check.status
    if check.status == 3:
        print("SKIP: ngspice or the pinned PDK is not installed on this machine.")
        for m in check.messages:
            print(f"  {m}")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        for m in check.messages:
            print(f"  {m}")
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    pdk_offenders = check_pdk_has_no_bare_gnd_node(pdk.resolve())
    if pdk_offenders:
        print(
            "FAIL: the pinned PDK names a node `GND`, which ngspice aliases onto "
            "global node 0 -- those devices would reach ground WITHOUT passing "
            "through this campaign's series network, and every arm would silently "
            "understate its effect. Re-derive the ground rename before running:",
            file=sys.stderr,
        )
        for offender in pdk_offenders:
            print(f"  {offender}", file=sys.stderr)
        return 1

    if tb.FRAGMENT_PATH.read_text() != tb.fragment_text():
        print(
            "FAIL: sim/full-conversion-transient/testbench/"
            "full_conversion_tb_fragment.spice is stale against its generator -- "
            "regenerate it before running.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="supply-impedance-") as scratch_name:
        scratch = Path(scratch_name)
        log_cache = Path(args.log_cache).expanduser().resolve() if args.log_cache else None

        if args.cost_probe is not None:
            if args.null_sweep:
                probe_arms = [ARMS_BY_NAME[CONTROL_ARM]] + null_sweep_arms(null_rsub_values)
                anchor_name = null_sweep_arm_name(R_SUBX_OHM)
                what = "null-option substrate ladder"
            else:
                probe_arms = [ARMS_BY_NAME[CONTROL_ARM]] + sweep_arms(l_mults, rsubx_values)
                anchor_name = sweep_arm_name(1.0, R_SUBX_OHM)
                what = "R/L sweep box"
            print(
                f"Pricing the {what}: {len(probe_arms)} truncated "
                f"({args.cost_probe:g} ns) transients, one at a time. This measures "
                "nothing about the DUT and writes no record."
            )
            rows = run_cost_probe(probe_arms, args.cost_probe, scratch, args.quiet)
            print("")
            for line in cost_probe_lines(rows, args.cost_probe, anchor_name):
                print(line)
            return 1 if any(row["trouble"] for row in rows) else 0

        if args.null_sweep:
            arms = [ARMS_BY_NAME[CONTROL_ARM]] + null_sweep_arms(null_rsub_values)
            print(
                f"Running the bounded null-option substrate ladder at the baseline "
                f"corner: {len(null_rsub_values)} points + the `{CONTROL_ARM}` "
                f"control = {len(arms)} full-conversion transients:"
            )
        elif args.sweep:
            # The control runs FIRST (every delta is taken against it) and the
            # inductance ladder ascends, so an interrupted sweep leaves the
            # cheapest, most-reusable points on disk rather than none of them.
            arms = [ARMS_BY_NAME[CONTROL_ARM]] + sweep_arms(l_mults, rsubx_values)
            print(
                f"Running the bounded R/L sweep at the baseline corner: "
                f"{len(l_mults)} x {len(rsubx_values)} grid points + the "
                f"`{CONTROL_ARM}` control = {len(arms)} full-conversion transients:"
            )
        else:
            arms = [ARMS_BY_NAME[name] for name in arm_names]
            n_corners = 9 if args.corners else 1
            print(
                f"Running {len(arms)} arm(s) x {n_corners} corner point(s) = "
                f"{len(arms) * n_corners} full-conversion transients:"
            )

        points, dut_netlist_text = run_campaign(
            arms, args.corners, args.quiet, scratch, log_cache=log_cache
        )

        print("")
        if args.null_sweep:
            control = next((p for p in points if p["arm"] == CONTROL_ARM), None)
            for line in null_sweep_findings_lines(points, control, null_rsub_values):
                print(line)
            if args.record:
                write_null_sweep_record(
                    points, dut_netlist_text, null_rsub_values, args.supersedes
                )
        elif args.sweep:
            control = next((p for p in points if p["arm"] == CONTROL_ARM), None)
            for line in sweep_findings_lines(points, control, l_mults, rsubx_values):
                print(line)
            if args.record:
                write_sweep_record(
                    points, dut_netlist_text, l_mults, rsubx_values, args.supersedes
                )
        else:
            controls = {p["corner_id"]: p for p in points if p["arm"] == CONTROL_ARM}
            for line in findings_lines(
                points, controls, arm_names, sorted({p["corner_id"] for p in points})
            ):
                print(line)
            if args.record:
                write_record(points, dut_netlist_text, args.corners, arm_names, args.supersedes)

    return 1 if any(p["missing"] for p in points) else 0


if __name__ == "__main__":
    raise SystemExit(main())

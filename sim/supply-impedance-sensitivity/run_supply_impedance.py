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
                    R+L.

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
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
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
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    deck = assemble_deck(dut_netlist_text, pdk_info, arm, process_corner, temp_c, supply_v)
    t0 = time.time()
    log_text = toolchain.run_ngspice_with_retry(
        deck, scratch, f"supply_impedance_{arm.name}_{cid}", attempts=3
    )
    wall_s = time.time() - t0

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
        point_id=f"{arm.name}@{cid}",
        extras={name: parsed.get(name) for name in extra_measure_names(arm)},
        missing=missing,
        log_text=log_text,
        deck_text=deck,
        wall_s=wall_s,
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
    arm_names: list[str], corners_mode: bool, quiet: bool, scratch: Path
) -> tuple[list[dict], str]:
    pdk_info = pdk.resolve()
    dut_netlist_text = fc.dut_text()

    if corners_mode:
        grid = corners_mod.ratified_oat_grid(
            NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )
    else:
        grid = [BASELINE_CORNER]

    points: list[dict] = []
    for arm_name in arm_names:
        arm = ARMS_BY_NAME[arm_name]
        for process_corner, temp_c, supply_v in grid:
            point = run_point(
                dut_netlist_text, pdk_info, scratch, arm, process_corner, temp_c, supply_v
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


def arm_table_lines(arms_run: list[str]) -> list[str]:
    out = [
        "| arm | " + " | ".join(f"`{t}`" for t in TERMINAL_ORDER) + " | what it isolates |",
        "|---" * (len(TERMINAL_ORDER) + 2) + "|",
    ]
    for name in arms_run:
        arm = ARMS_BY_NAME[name]
        cells = " | ".join(_bond_cell(arm, t) for t in TERMINAL_ORDER)
        out.append(f"| `{name}` | {cells} | {arm.summary} |")
    out.append("")
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
    """
    parts = ["sim/supply-impedance-sensitivity/run_supply_impedance.py"]
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
    lines.extend(arm_table_lines(arms_run))
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
        "magnitude\"."
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
            a(f"| `{cid}` | `{name}` | {p['wall_s']:.0f} | {ratio} |")
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
        if "no-gnd-pad" in omitted_arms:
            a(
                "- **`no-gnd-pad`** (DR-012's rejected null option) is omitted on "
                "**cost**, not on merit. Its ground is a high-impedance, "
                "lightly-damped node, which drives the transient solver's timestep "
                "down hard: a bounded calibration slice of the same deck measured "
                "it at roughly an order of magnitude more wall clock per simulated "
                "nanosecond than the control arm, which projects to several hours "
                "for one run of this stimulus. It is implemented, it is reachable "
                "with `--arms`, and it remains the arm that would price DR-012's "
                "rejected alternative directly -- so the conclusions below are "
                "about the *cost of the bonded return*, and say nothing about what "
                "the null option would have cost."
            )
            a("")

    if not corners_mode:
        a("## Subset-corner justification (`sim/README.md`)")
        a("")
        a(
            "This record runs the arm comparison at "
            f"{len(corner_ids)} point(s) of the ratified corner set "
            f"({', '.join('`' + c + '`' for c in corner_ids)}), not all nine. "
            "Three separate constraints bind, and none of them is a judgement "
            "that the corners do not matter:"
        )
        a("")
        a(
            "- **Host policy.** The machine this record was produced on is a "
            "shared dispatch worker whose operating rules forbid running a "
            "multi-corner ngspice grid locally; a grid there must be expressed as "
            "a `klt sim` request and submitted to an EDA batch fleet. Sequential "
            "single-corner runs are the shape those rules do allow, and that is "
            "what the table above is."
        )
        a(
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
        )
        a(
            "- **Cost.** The nine-point ratified grid across "
            f"{len(arms_run)} arms is {9 * len(arms_run)} whole-ADC transients. "
            "At the per-run cost measured above that is a campaign in its own "
            "right, not a longer version of this one."
        )
        a("")
        a(
            "So the ratified-grid run is **deferred, not skipped**: the runner "
            "already implements it (`--corners`, the nine-point "
            "`ratified_oat_grid()` x the arms) and this experiment's README names "
            "the exact command. What it needs is a host whose ngspice satisfies "
            "the pin and whose policy allows a grid -- not more code. Until then, "
            "no statement in this record is a corner-worst-case claim; it is a "
            "mechanism comparison at the baseline corner."
        )
        a("")

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
    between them is bond inductance's own contribution, and it is the one number
    in this record that isolates a single mechanism rather than comparing two
    whole grounding schemes. Deliberately NOT computed against `substrate`: that
    arm's resistance is ~300x the package resistance, so it differs from
    `package` in two elements at once and a difference against it would confound
    them.
    """
    if not {"package", "package-r-only"} <= set(arms_run):
        return [
            "- **Bond-inductance ablation not available in this record**: it needs "
            "both the `package` and `package-r-only` arms, and this run did not "
            "include both."
        ]
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
            + f"; analog-ground excursion {pp_txt}. This is the only "
            "single-mechanism number in this record."
        )
    return out


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
        default=",".join(arm.name for arm in ARMS),
        help="comma-separated subset of the supply-return arms to run (default: all)",
    )
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--supersedes",
        default="",
        metavar="RECORD_ID",
        help="record-id of the prior record of THIS experiment that the new record "
        "replaces for the same claim (sim/README.md's append-only convention)",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    arm_names = [name.strip() for name in args.arms.split(",") if name.strip()]
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
        n_corners = 9 if args.corners else 1
        print(
            f"Running {len(arm_names)} arm(s) x {n_corners} corner point(s) = "
            f"{len(arm_names) * n_corners} full-conversion transients:"
        )
        points, dut_netlist_text = run_campaign(arm_names, args.corners, args.quiet, scratch)

        controls = {p["corner_id"]: p for p in points if p["arm"] == CONTROL_ARM}
        print("")
        for line in findings_lines(
            points, controls, arm_names, sorted({p["corner_id"] for p in points})
        ):
            print(line)

        if args.record:
            write_record(points, dut_netlist_text, args.corners, arm_names, args.supersedes)

    return 1 if any(p["missing"] for p in points) else 0


if __name__ == "__main__":
    raise SystemExit(main())

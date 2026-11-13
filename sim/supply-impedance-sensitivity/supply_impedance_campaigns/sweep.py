"""The bounded 2-D R/L sweep campaign (`--sweep`, issue #409 item 3).

Issue #848's split of `run_supply_impedance.py`. This module owns the box's
two axis tuples, its arm builders, its findings prose and its record writer.
Imports `common` only.

`SWEEP_L_MULTIPLIERS` and `SWEEP_RSUBX_OHM` are read as SOURCE TEXT by
`docs/chipalooza/check_proposal_citations.py` (`SWEEP_AXES_SOURCE`), which
recognises a module-level tuple literal and reports anything else as an
ungraded silence. Keep both at column 0, annotated, with a literal tuple on
the same line as the `=`.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .common import (
    ARMS_BY_NAME,
    Arm,
    Bond,
    CONTROL_ARM,
    GND_DIE,
    NOMINAL_SUPPLY_V,
    PACKAGE_L_H,
    PACKAGE_R_OHM,
    RUNNER_REL,
    R_SUBX_OHM,
    SWEEP_BASE_ARM,
    TERMINAL_ORDER,
    _assumption_lines,
    _captured_code_table_lines,
    _mv,
    _open_corners_record,
    _provenance_bullet,
    _rail_current_table_lines,
    _stimulus_bullet,
    _wall_clock_table_lines,
    arm_network_lines,
    arm_table_lines,
    subset_corner_lines,
    tb,
    worst_mid_scale_delta,
)
from harness import corners as corners_mod, evidence


# --------------------------------------------------------------------------
# The bounded 2-D R/L sweep (issue #409 item 3; DR-015's own open item)
# --------------------------------------------------------------------------
# The five arms of `common.ARMS` are five NETWORKS at ONE point of DR-015's
# assumed magnitudes. That shows whether the mechanism matters at that point;
# it cannot show the magnitude at which it starts to. DR-015 says so itself, in
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
# different experiment with a different reading: `--null-sweep`, in
# `null_sweep.py`. Every record this sweep writes says which of the two it
# moved rather than letting "substrate resistance" be read as both.

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
            "`design/sar_adc_top.spice` carries is in the deck (DR-017 added one "
            "`cap_mim_m3_1` per supply domain; DR-015 item 6's `no decoupling is "
            "modelled` premise held only before that). **No BOARD decoupling is "
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
    prov, lines, corner_ids, processes, temps, supplies = _open_corners_record(
        points, dut_netlist_text
    )

    grid_points = [p for p in points if p["arm"] != CONTROL_ARM]
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
    a(_provenance_bullet())
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Grid**: {len(l_mults)} bond-inductance multipliers x "
        f"{len(rsubx_values)} substrate-link resistances = {len(grid_points)} swept "
        f"points, plus the `{CONTROL_ARM}` control, at {len(corner_ids)} corner "
        f"point(s) = {len(points)} whole-ADC transients. Every swept point is the "
        f"as-built `{SWEEP_BASE_ARM}` topology (all four supply terminals bonded, "
        "DR-012's chosen shape) with exactly those two elements moved."
    )
    a(_stimulus_bullet())
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
    lines.extend(_captured_code_table_lines(points, control, "point"))
    a("")

    a("## Rail excursion and average current per point")
    a("")
    lines.extend(_rail_current_table_lines(points, "point"))

    a("## Findings")
    a("")
    for line in sweep_findings_lines(points, control, l_mults, rsubx_values):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    lines.extend(_wall_clock_table_lines(points, control, "point"))
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
        "since DR-017 (issue #431) that is one `cap_mim_m3_1` per supply domain, "
        "and DR-015 item 6's `no decoupling is modelled` premise no longer holds. "
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

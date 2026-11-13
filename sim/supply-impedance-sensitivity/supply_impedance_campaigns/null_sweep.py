"""The bounded null-option substrate ladder (`--null-sweep`, issue #409).

Issue #848's split of `run_supply_impedance.py`. This module owns the
ladder's own axis tuple, its arm builders, its findings prose and its record
writer. Imports `common` only.

`NULL_SWEEP_RSUBX_OHM` is read as SOURCE TEXT by
`docs/chipalooza/check_proposal_citations.py` (`NULL_SWEEP_AXIS_SOURCE`),
which recognises a module-level tuple literal and reports anything else as an
ungraded silence. Keep it at column 0, annotated, with a literal tuple on the
same line as the `=`.
"""
from __future__ import annotations

from pathlib import Path

from .common import (
    ARMS_BY_NAME,
    Arm,
    CONTROL_ARM,
    NOMINAL_SUPPLY_V,
    PACKAGE_L_H,
    PACKAGE_R_OHM,
    RUNNER_REL,
    R_SUBX_OHM,
    SWEEP_BASE_ARM,
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
    prov, lines, corner_ids, processes, temps, supplies = _open_corners_record(
        points, dut_netlist_text
    )

    swept = [p for p in points if p["arm"] != CONTROL_ARM]
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
    a(_provenance_bullet())
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Ladder**: {len(swept)} substrate-return resistances plus the "
        f"`{CONTROL_ARM}` control, at {len(corner_ids)} corner point(s) = "
        f"{len(points)} whole-ADC transients. Every swept point is the "
        f"`{NULL_SWEEP_BASE_ARM}` topology (`GND` unbonded; `VDD`/`VPWR`/`VGND` at "
        "DR-015's R+L) with exactly one element moved."
    )
    a(_stimulus_bullet())
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
    lines.extend(_captured_code_table_lines(points, control, "point"))
    a("")

    a("## Rail excursion and average current per point")
    a("")
    lines.extend(
        _rail_current_table_lines(
            points,
            "point",
            extra_note=(
                "`I(GND)` is `n/a (no bond)` on every swept row by construction: this "
                "topology's whole point is that the analog ground has no bond current "
                "to measure, because it has no bond."
            ),
        )
    )

    a("## Findings")
    a("")
    for line in null_sweep_findings_lines(points, control, rsubx_values):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    lines.extend(_wall_clock_table_lines(points, control, "point"))
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

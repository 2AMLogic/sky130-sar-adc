"""The decoupling-tie ESR ladder campaign (`--decap-esr`, issue #465).

Issue #848's split of `run_supply_impedance.py`. This module owns the ladder's
rungs, the committed layout record it reads its measured tie resistances out
of, its arm builders, its verdict, its findings prose and its record writer.
Imports `common` only.

The deck-patching half of the decoupling tie (`DECAP_TIE_RECORD`,
`DECAP_DEVICES`, `DECAP_DEVICE_MODEL`, `_decap_node`, `_decap_tie_instance`
and `patch_dut_decap_ties` itself) lives in `common`, because every campaign's
deck assembly goes through it -- not only this one's.
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path

from .common import (
    ARMS_BY_NAME,
    Arm,
    BASELINE_CORNER,
    CONTROL_ARM,
    DECAP_DEVICES,
    DECAP_TIE_RECORD,
    PACKAGE_L_H,
    RAIL_PROBES,
    REPO_ROOT,
    RUNNER_REL,
    R_SUBX_OHM,
    TERMINAL_ORDER,
    _assumption_lines,
    _avg_current_cells,
    _captured_code_table_lines,
    _mv,
    _open_corners_record,
    _stimulus_bullet,
    _wall_clock_table_lines,
    arm_network_lines,
    arm_table_lines,
    patch_dut_decap_ties,
    patch_dut_ground,
    subset_corner_lines,
    tb,
    worst_mid_scale_delta,
)
from harness import corners as corners_mod, evidence
import run_conversion as fc


# --------------------------------------------------------------------------
# The decoupling-tie ESR ladder (`--decap-esr`, issue #465)
# --------------------------------------------------------------------------
# WHAT GAP THIS CLOSES. DR-017 put one `cap_mim_m3_1` pair per supply domain
# into `design/sar_adc_top.spice`, and that netlist connects each pair to its
# two rails through ideal wires -- the only series resistance in it is the PDK
# MiM subcircuit's own plate resistance (`r1 = rm3*l/w`, 0.0235 Ohm for the
# shipped pair). The DRAWN ties are not ideal. Issue #440 placed them and
# measured them with `layout/sar-adc-top/bin/probe-decap-sites.py`, a lumped DC
# ladder assembled from `build_layout.py`'s own geometry constants and the PDK's
# own sheet/via resistances:
#
#     analog  (`VDD`/`GND`)   13.837 Ohm per domain
#     digital (`VPWR`/`VGND`) 13.448 Ohm per domain
#
# about 590x the device's own ESR, and ~80 % of it single-cut vias. Nothing in
# this repo has ever simulated a netlist containing it, so every decoupled
# record this campaign has minted measures a better-connected capacitor than the
# one on the die.
#
# WHY IT IS A SIGN QUESTION AND NOT AN OBVIOUS IMPROVEMENT. A 2x2 via array at
# each riser and each plate entry would cut that resistance roughly 3x, and #440
# deliberately did not draw one, because which way the change moves the rails is
# not obvious:
#
#   * The pair's own reactance at the DR-015 package resonance (1221.5 MHz for
#     8.870 pF against 1.914 nH) is 14.69 Ohm, so at the as-built ESR the
#     quality factor of that resonance is Q ~ 1.06 (analog) / 1.09 (digital) --
#     critically-damped-ish. Removing the ESR raises Q, which sharpens the
#     resonance as much as it lowers the impedance at it, and a lightly damped
#     tank rings longer after every switching edge.
#   * Read the other way, ESR does not reach the pair's own reactance until
#     ~1.3 GHz, so at the frequencies the bounce lives at the pair is already
#     reactance-dominated and 13.8 -> 4.5 Ohm should buy little.
#
# Both arguments are design-time inferences. This ladder is the measurement.
#
# WHAT IS MOVED, AND WHAT IS NOT. Exactly one thing: the four tie resistors.
# Every rung is the as-built `package` topology (all four supply terminals
# bonded through DR-015's R+L, the same lumped `R_SUBX`, the same stimulus) with
# the measured tie resistance scaled by one multiplier. The `0x` rung emits no
# tie resistors at all -- it is the committed netlist card for card, the
# idealisation the campaign's existing decoupled records measured -- and that
# identity is asserted before the run (`decap_esr_anchor_matches_base_arm()`)
# rather than described. So the difference between two rungs is the tie
# resistance's own contribution and nothing else (DR-015 item 5's requirement).
#
# WHAT THESE RESISTORS ARE, AND ARE NOT. They are a MEASUREMENT of this repo's
# own drawn layout, not an assumption like DR-015's R+L: their provenance is a
# committed layout record id, and the runner reads the values out of that
# record's own `decap-ties.json` rather than carrying a hand-typed number. But
# they are a LUMPED DC ladder: one resistor per tie, no frequency dependence, no
# skin effect, and above all **no interconnect inductance** -- the other half of
# DR-017's routing-parasitics open item, which needs `klt pex` and the
# device/net correspondence this flow does not yet have (klayout-tools#1878),
# and which stays out of scope here.
DECAP_ESR_BASE_ARM = "package"

#: Multipliers of the MEASURED per-tie resistance. `0` is the committed
#: netlist (no tie resistance at all), `1` is the layout as drawn. Two rungs on
#: purpose: each one is a whole-ADC transient of the expensive `package` shape,
#: and the sign of the difference between these two is the entire question
#: issue #465 asks. A third rung at the 2x2-via-array projection would quantify
#: what the arrays recover, and is only worth its hour if this pair says the
#: arrays are worth drawing at all.
DECAP_ESR_MULTIPLIERS: tuple[float, ...] = (0.0, 1.0)

#: How far apart two rungs' excursions must be before the ladder is read as
#: having a DIRECTION. A stated reading threshold, not a measured uncertainty:
#: these are `.meas`-reported peak-to-peak values from one deterministic
#: transient each, so the band exists to stop a sub-percent difference being
#: reported as a mechanism, not because the solver's own noise is known.
DECAP_ESR_WASH_BAND = 0.02

#: Supply terminal -> the `ties` key `decap-ties.json` reports that terminal's
#: own drawn tie under.
DECAP_TIE_KEYS: dict[str, str] = {
    "VDD": "VDD (analog supply -> both top plates)",
    "GND": "GND (analog return -> both bottom plates)",
    "VPWR": "VPWR (digital supply -> both top plates)",
    "VGND": "VGND (digital return -> both bottom plates)",
}


@dataclass(frozen=True)
class DecapTieMeasurement:
    """One committed layout record's measured decoupling-tie resistances."""

    record: str
    #: supply terminal -> the drawn tie's lumped resistance, in ohms
    tie_ohm: dict[str, float]
    #: domain -> that domain's total interconnect ESR (its two ties in series)
    esr_ohm: dict[str, float]
    capacitance_f: float
    q_at_resonance: dict[str, float]
    reactance_at_resonance_ohm: dict[str, float]
    package_resonance_hz: float
    esr_equals_reactance_hz: dict[str, float]

    def domain_esr_line(self, mult: float = 1.0) -> str:
        return ", ".join(
            f"{domain} {ohms * mult:.3f} Ohm" for domain, ohms in self.esr_ohm.items()
        )


@functools.lru_cache(maxsize=None)
def load_decap_ties(record: str = DECAP_TIE_RECORD) -> DecapTieMeasurement:
    """The measured tie resistances, read out of a committed layout record.

    Never a hand-typed number: the values below are exactly the ones
    `layout/sar-adc-top/bin/probe-decap-sites.py` derived from the drawn
    geometry and the PDK's own sheet/via resistances, and the record id they
    came from reaches this campaign's own record so a reader can re-derive them.

    Every guard here refuses rather than degrades. In particular
    `model_matches_drawn_geometry` is the probe's own statement that each `Wire`
    of its ladder is a rectangle the layout really drew; a record whose probe
    said otherwise is not a measurement of anything, and simulating its numbers
    would put a resistance in an append-only sim record that no layout ever had.
    """
    path = REPO_ROOT / record / "decap-ties.json"
    if not path.is_file():
        raise RuntimeError(
            f"no decap-ties.json under {record}/ -- the decoupling-tie ESR ladder "
            "reads its resistances out of a committed layout record (issue #440's "
            "`probe-decap-sites.py`), and cannot run without one."
        )
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{record}/decap-ties.json is not readable JSON: {exc}") from exc
    if data.get("schema_version") != 1:
        raise RuntimeError(
            f"{record}/decap-ties.json is schema_version "
            f"{data.get('schema_version')!r}, not 1 -- re-derive this ladder against "
            "the new schema before running it."
        )
    if not data.get("model_matches_drawn_geometry", False) or data.get("model_problems"):
        raise RuntimeError(
            f"{record}/decap-ties.json reports that its own resistance model does "
            "NOT match the drawn geometry "
            f"({data.get('model_problems')}) -- those ohms describe a layout that "
            "was not built, so they may not be simulated."
        )
    ties = data.get("ties") or {}
    tie_ohm: dict[str, float] = {}
    for terminal, key in DECAP_TIE_KEYS.items():
        entry = ties.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("tie_ohm"), (int, float)):
            raise RuntimeError(
                f"{record}/decap-ties.json has no `ties[{key!r}].tie_ohm` -- the "
                "probe's report changed shape; re-derive this ladder."
            )
        value = float(entry["tie_ohm"])
        if value <= 0.0:
            raise RuntimeError(
                f"{record}/decap-ties.json reports a non-physical tie resistance "
                f"for {terminal}: {value} Ohm"
            )
        tie_ohm[terminal] = value
    per_domain = data.get("per_domain") or {}
    esr_ohm = {k: float(v) for k, v in (per_domain.get("esr_ohm") or {}).items()}
    for _inst, domain, terminals in DECAP_DEVICES:
        if domain not in esr_ohm:
            raise RuntimeError(
                f"{record}/decap-ties.json has no per-domain ESR for {domain!r} -- "
                "the probe's report changed shape; re-derive this ladder."
            )
        legs = sum(tie_ohm[t] for t in terminals)
        # Both sides are rounded to 3 decimals by the probe, so the sum of two
        # of them can differ from the reported total in the last digit; a
        # larger gap means the two halves of that file disagree about the same
        # domain and neither may be simulated.
        if abs(legs - esr_ohm[domain]) > 2e-3:
            raise RuntimeError(
                f"{record}/decap-ties.json disagrees with itself for {domain}: its "
                f"two ties sum to {legs:.3f} Ohm but its per-domain ESR is "
                f"{esr_ohm[domain]:.3f} Ohm."
            )
    capacitance_f = float(per_domain.get("capacitance_F") or 0.0)
    if capacitance_f <= 0.0:
        raise RuntimeError(
            f"{record}/decap-ties.json reports no per-domain capacitance -- the "
            "probe's report changed shape; re-derive this ladder."
        )
    return DecapTieMeasurement(
        record=record,
        tie_ohm=tie_ohm,
        esr_ohm=esr_ohm,
        capacitance_f=capacitance_f,
        q_at_resonance={k: float(v) for k, v in (per_domain.get("q_at_resonance") or {}).items()},
        reactance_at_resonance_ohm={
            k: float(v) for k, v in (per_domain.get("reactance_at_resonance_ohm") or {}).items()
        },
        package_resonance_hz=float(per_domain.get("package_resonance_Hz") or 0.0),
        esr_equals_reactance_hz={
            k: float(v) for k, v in (per_domain.get("esr_equals_reactance_Hz") or {}).items()
        },
    )


def decap_esr_arm_name(mult: float) -> str:
    """The rung's arm name -- also its log/deck filename and its cache key.
    Prefixed distinctly from `sweep_arm_name()` / `null_sweep_arm_name()` so a
    point of this ladder can never collide with, or be mistaken for, a point of
    either sweep in a cache directory or a records listing."""
    return f"decapesr-{mult:g}x"


def decap_esr_arm(mult: float, ties: DecapTieMeasurement) -> Arm:
    """One rung: the as-built topology with `mult` x the measured tie resistance.

    The bonds are taken from the base arm itself rather than re-asserted from
    `PACKAGE_R_OHM`/`PACKAGE_L_H`, so this ladder follows the arm it moves
    around instead of drifting from it, and only the tie resistance moves.

    `mult == 0` emits NO tie resistors rather than four zero-valued ones: a
    0 Ohm resistor is a different (degenerate) element with two extra nodes, and
    the whole point of that rung is to be the committed netlist card for card.
    """
    base = ARMS_BY_NAME[DECAP_ESR_BASE_ARM]
    if set(base.bonds) != set(TERMINAL_ORDER) or any(b is None for b in base.bonds.values()):
        raise RuntimeError(
            f"the decap-ESR ladder's base arm `{DECAP_ESR_BASE_ARM}` no longer bonds "
            "all four supply terminals through an impedance -- the topology the ties "
            "are being added to is not the as-built one any more; re-derive the "
            "ladder before running it."
        )
    if mult < 0.0:
        raise RuntimeError(
            f"decap-ESR rung ({mult}) is not physical: an interconnect resistance "
            "multiplier must be >= 0"
        )
    triples: tuple[tuple[str, str, float], ...] = ()
    if mult > 0.0:
        triples = tuple(
            (instance, terminal, ties.tie_ohm[terminal] * mult)
            for instance, _domain, terminals in DECAP_DEVICES
            for terminal in terminals
        )
    if mult == 0.0:
        summary = (
            f"as-built `{DECAP_ESR_BASE_ARM}` topology with NO decoupling-tie "
            "interconnect resistance -- the committed netlist card for card, which is "
            "the idealisation every decoupled record in this campaign has measured"
        )
    else:
        summary = (
            f"as-built `{DECAP_ESR_BASE_ARM}` topology with {mult:g}x the MEASURED "
            f"drawn decoupling-tie resistance ({ties.domain_esr_line(mult)} per "
            "domain, in series with that domain's own MiM pair) from "
            f"`{ties.record}`"
        )
    return Arm(
        name=decap_esr_arm_name(mult),
        summary=summary,
        bonds=dict(base.bonds),
        substrate=base.substrate,
        decap_ties=triples,
    )


def decap_esr_arms(mults: tuple[float, ...], ties: DecapTieMeasurement) -> list[Arm]:
    """The ladder, in the order given. The caller runs it ascending so an
    interrupted campaign leaves the rung that ties this record to the existing
    decoupled records (`0x`) on disk first."""
    return [decap_esr_arm(m, ties) for m in mults]


def decap_esr_anchor_matches_base_arm(ties: DecapTieMeasurement) -> bool:
    """Is the `0x` rung card-for-card the committed `package` arm?

    Same contract, and same reason, as `sweep_anchor_matches_base_arm()` -- but
    checked on BOTH halves of the deck this mode touches, because this ladder is
    the first thing in the campaign that rewrites the DUT body as well as the
    arm network. Without the tie, the ladder would still run and still write a
    plausible record while being anchored to nothing.
    """
    anchor = decap_esr_arm(0.0, ties)
    base = ARMS_BY_NAME[DECAP_ESR_BASE_ARM]
    anchor_net = [
        line for line in arm_network_lines(anchor) if line and not line.startswith("*")
    ]
    base_net = [line for line in arm_network_lines(base) if line and not line.startswith("*")]
    body, _hits = patch_dut_ground(fc.dut_text())
    anchor_body, anchor_ties = patch_dut_decap_ties(body, anchor)
    base_body, base_ties = patch_dut_decap_ties(body, base)
    return (
        anchor_net == base_net
        and anchor_body == base_body == body
        and anchor_ties == base_ties == []
    )
# --------------------------------------------------------------------------
# The decoupling-tie ESR ladder's own record
# --------------------------------------------------------------------------
def decap_esr_invocation_line(mults: tuple[float, ...], supersedes: str) -> str:
    """The `--decap-esr` counterpart of `invocation_line()`, under the same
    rules: a flag that changes what was simulated is stated, one that only
    changes how the run was scheduled (`--log-cache`) is not. The ladder flag
    appears only when the run departed from the documented rungs, so the default
    run's footer is exactly the command `sim/spec-coverage.json` indexes."""
    parts = [RUNNER_REL, "--decap-esr"]
    if tuple(mults) != DECAP_ESR_MULTIPLIERS:
        parts.append("--decap-esr-mult " + ",".join(f"{m:g}" for m in mults))
    parts.append("--record")
    if supersedes:
        parts.append(f"--supersedes {supersedes}")
    return " ".join(parts)


def _decap_esr_point(points: list[dict], mult: float) -> dict | None:
    name = decap_esr_arm_name(mult)
    return next((p for p in points if p["arm"] == name), None)


def decap_esr_verdict(
    points: list[dict], mults: tuple[float, ...], band: float = DECAP_ESR_WASH_BAND
) -> dict:
    """Which way the MEASURED tie resistance moves the die-side rails.

    This is the whole deliverable of issue #465, so it is computed rather than
    written: the `1x` rung's peak-to-peak excursion on each of the four die-side
    rails, against the `0x` rung's, with a stated reading band
    (`DECAP_ESR_WASH_BAND`) below which a difference is called a wash instead of
    a direction. A `mixed` verdict -- some rails up, some down, by more than the
    band -- is reported as `mixed` rather than resolved by picking a favourite
    rail: four rails disagreeing IS the finding in that case.

    `direction` is about the SIGN of adding the drawn resistance. The question
    the layout actually asks is the reverse one (would cutting it help?), which
    is the same measurement read backwards: `damping` means the drawn ties
    lower the excursion, so cutting them with via arrays would raise it.
    """
    zero = _decap_esr_point(points, 0.0)
    built = _decap_esr_point(points, 1.0)
    out: dict = {
        "available": False,
        "band": band,
        "per_rail": {},
        "direction": "unavailable",
        "worst_0x": None,
        "worst_1x": None,
        "code_delta": None,
    }
    if 0.0 not in mults or 1.0 not in mults or zero is None or built is None:
        return out
    per_rail: dict[str, float | None] = {}
    for probe, _node, _label in RAIL_PROBES:
        a = zero["extras"].get(f"{probe}_pp")
        b = built["extras"].get(f"{probe}_pp")
        per_rail[probe] = None if a is None or b is None or a <= 0.0 else b / a
    ratios = [r for r in per_rail.values() if r is not None]
    if not ratios:
        out["per_rail"] = per_rail
        return out
    seen = set()
    for ratio in ratios:
        if ratio < 1.0 - band:
            seen.add("damping")
        elif ratio > 1.0 + band:
            seen.add("amplifying")
        else:
            seen.add("wash")
    if seen == {"wash"}:
        direction = "wash"
    elif seen <= {"damping", "wash"}:
        direction = "damping"
    elif seen <= {"amplifying", "wash"}:
        direction = "amplifying"
    else:
        direction = "mixed"
    pps_zero = [zero["extras"].get(f"{p}_pp") for p, _n, _l in RAIL_PROBES]
    pps_built = [built["extras"].get(f"{p}_pp") for p, _n, _l in RAIL_PROBES]
    out.update(
        available=True,
        per_rail=per_rail,
        direction=direction,
        worst_0x=max([v for v in pps_zero if v is not None], default=None),
        worst_1x=max([v for v in pps_built if v is not None], default=None),
        code_delta=worst_mid_scale_delta(built, zero),
    )
    return out


#: What each verdict direction means for the geometry question issue #465 asks:
#: should `build_layout.py` draw 2x2 via arrays at the decoupling ties?
DECAP_ESR_VIA_ARRAY_READING: dict[str, str] = {
    "damping": (
        "**the via arrays are NOT worth drawing.** The drawn ties LOWER the die-side "
        "excursion, so cutting their resistance -- which is exactly what a 2x2 array "
        "at each riser and each plate entry would do -- moves the rails back toward "
        "the higher-excursion `0x` rung. The ~13.8 Ohm is damping the resonance the "
        "8.870 pF pair forms with DR-015's bond inductance (Q ~ 1.06), not spoiling "
        "the decoupling, so spending vias to remove it would make this measurement "
        "worse rather than better"
    ),
    "amplifying": (
        "**cutting the tie resistance is directionally worth something.** The drawn "
        "ties RAISE the die-side excursion, so a 2x2 via array at each riser and each "
        "plate entry -- which #440 projected at roughly a 3x reduction, to ~4-5 Ohm "
        "per domain -- would recover part of that difference. How much is NOT "
        "measured here: this ladder brackets the reachable value between its two "
        "rungs rather than running the projected array geometry itself, and the "
        "arrays cannot reach the `0x` rung (they can only reduce the via half of the "
        "ladder, and the metal half stays)"
    ),
    "wash": (
        "**the via arrays are NOT worth drawing.** The drawn ties move the die-side "
        "excursion by less than the stated reading band on every rail, so the "
        "reachable ~3x reduction has nothing measurable to recover. At the "
        "frequencies this stimulus excites, the pair is reactance-dominated and its "
        "series resistance is not what sets the excursion"
    ),
    "mixed": (
        "**no single verdict.** The four die-side rails do not agree on the sign by "
        "more than the stated reading band, so this record does not support a "
        "statement that cutting the tie resistance helps OR hurts. Reported as "
        "measured rather than resolved by choosing one rail"
    ),
    "unavailable": (
        "**not answerable from this record.** It needs both the `0x` and `1x` rungs, "
        "and this run did not produce both"
    ),
}


def decap_esr_findings_lines(
    points: list[dict],
    control: dict | None,
    mults: tuple[float, ...],
    ties: DecapTieMeasurement,
) -> list[str]:
    """What the ladder says, as differences between rungs."""
    out: list[str] = []

    out.append(
        "- **The ladder is anchored to the committed decoupled netlist.** Its "
        f"`{decap_esr_arm_name(0.0)}` rung emits no tie resistors at all, so it is "
        f"card for card the `{DECAP_ESR_BASE_ARM}` arm this campaign has already "
        "recorded on the same DUT: same per-terminal R+L, same lumped "
        f"`R_SUBX = {R_SUBX_OHM:g} Ohm`, same stimulus, same device cards. "
        + (
            "Checked before the run and again at record-write time "
            "(`decap_esr_anchor_matches_base_arm()`), on the arm network AND on the "
            "patched DUT body, so the ladder is tied to the existing records rather "
            "than merely described as being."
            if decap_esr_anchor_matches_base_arm(ties)
            else "**This check FAILED** -- the `0x` rung is no longer the committed "
            "netlist, so nothing below may be read as the tie resistance's own "
            "contribution."
        )
    )

    out.append(
        "- **Where the resistance comes from**: "
        f"`{ties.record}/decap-ties.json`, issue #440's measurement of the DRAWN "
        f"ties -- {ties.domain_esr_line()} per domain, read out of that record by "
        "this runner rather than typed in. It is a lumped DC ladder over the drawn "
        "straps and vias from the PDK's own sheet/via resistances: no frequency "
        "dependence, and **no interconnect inductance** (the other half of DR-017's "
        "routing-parasitics item, which needs `klt pex`, is not modelled here)."
    )

    for probe, _node, label in RAIL_PROBES:
        cells = []
        for m in mults:
            p = _decap_esr_point(points, m)
            pp = None if p is None else p["extras"].get(f"{probe}_pp")
            cells.append("n/a" if pp is None else f"{pp * 1e3:.3f} mV")
        out.append(
            f"- **{label}**: peak-to-peak die-side excursion "
            + " -> ".join(cells)
            + " as the drawn tie resistance goes "
            + " -> ".join(f"{m:g}x" for m in mults)
            + ". Only those four resistors move along this row."
        )

    verdict = decap_esr_verdict(points, mults)
    if verdict["available"]:
        ratios = ", ".join(
            f"{label.split('(')[0].strip()} "
            + (
                "n/a"
                if verdict["per_rail"].get(probe) is None
                else f"{verdict['per_rail'][probe]:.3f}x"
            )
            for probe, _node, label in RAIL_PROBES
        )
        worst_0 = verdict["worst_0x"]
        worst_1 = verdict["worst_1x"]
        out.append(
            "- **The sign, which is what this record exists to establish**: adding the "
            "measured drawn tie resistance to the committed netlist takes the worst "
            f"die-side rail excursion from **{worst_0 * 1e3:.3f} mV** to "
            f"**{worst_1 * 1e3:.3f} mV** peak-to-peak "
            f"({worst_1 / worst_0:.3f}x), per rail {ratios}, at a stated reading band "
            f"of +-{verdict['band'] * 100:g} %. Worst mid-scale |delta code| between "
            "the two rungs = "
            + ("n/a" if verdict["code_delta"] is None else f"**{verdict['code_delta']} LSB**")
            + f". Direction: **{verdict['direction']}**."
        )
    out.append(
        "- **What that means for the drawn geometry**: "
        + DECAP_ESR_VIA_ARRAY_READING[verdict["direction"]]
        + ". One corner (`"
        + corners_mod.corner_id(*BASELINE_CORNER)
        + "`), DR-015's assumed package magnitudes, no board decoupling, and a "
        "DC-only tie model -- so this is a directional finding about this stimulus at "
        "this corner, not a universal statement about decoupling ESR."
    )

    if control is not None:
        moved = []
        for m in mults:
            p = _decap_esr_point(points, m)
            if p is None:
                continue
            delta = worst_mid_scale_delta(p, control)
            if delta:
                moved.append((m, delta))
        if moved:
            out.append(
                "- **A mid-scale captured code moves on this ladder** (against the "
                f"`{CONTROL_ARM}` control): "
                + ", ".join(f"`{m:g}x` = {d} LSB" for m, d in moved)
                + f"; {len(moved)} of {len(mults)} rungs move at least one mid-scale "
                "code."
            )
        else:
            out.append(
                f"- **No mid-scale captured code moves on this ladder.** Every rung "
                f"reproduces the `{CONTROL_ARM}` control's mid-scale codes exactly "
                "(worst |delta code| = **0 LSB**), so the tie resistance changes the "
                "rails' own excursion without changing a captured code at this "
                "corner -- a bounded null result on the code axis, not a null on the "
                "excursion axis."
            )

    missing_points = [p["point_id"] for p in points if p["missing"]]
    if missing_points:
        out.append(
            "- **Incomplete runs** (some `.meas` value did not come back): "
            + ", ".join(f"`{pid}`" for pid in missing_points)
            + " -- reported rather than dropped."
        )
    return out


def _decap_tie_table_lines(ties: DecapTieMeasurement) -> list[str]:
    """The measured tie resistances, as the record states them."""
    out = [
        "| drawn tie | lumped resistance | domain | domain ESR | Q at the package "
        "resonance | ESR = X_C at |",
        "|---|---|---|---|---|---|",
    ]
    for instance, domain, terminals in DECAP_DEVICES:
        for terminal in terminals:
            key = DECAP_TIE_KEYS[terminal]
            out.append(
                f"| `{key}` | {ties.tie_ohm[terminal]:.3f} Ohm | {domain} | "
                f"**{ties.esr_ohm[domain]:.3f} Ohm** | "
                f"{ties.q_at_resonance.get(domain, float('nan')):.3f} | "
                f"{ties.esr_equals_reactance_hz.get(domain, 0.0) / 1e9:.3f} GHz |"
            )
    out.append("")
    out.append(
        f"Each domain's ESR is its two ties in series, carrying its {ties.capacitance_f * 1e12:.3f} "
        f"pF pair. `Q` and the crossover are the probe's own, at the "
        f"{ties.package_resonance_hz / 1e6:.1f} MHz resonance that capacitance forms "
        f"with DR-015's per-terminal {PACKAGE_L_H * 1e9:.3f} nH; the pair's reactance "
        "there is "
        + ", ".join(
            f"{v:.2f} Ohm ({k})" for k, v in ties.reactance_at_resonance_ohm.items()
        )
        + "."
    )
    return out


def write_decap_esr_record(
    points: list[dict],
    dut_netlist_text: str,
    mults: tuple[float, ...],
    ties: DecapTieMeasurement,
    supersedes: str = "",
) -> Path:
    """The `--decap-esr` record.

    A separate writer from `write_record()` and from the two sweep writers, for
    the same reason they are separate from each other: the records make different
    claims and must not be able to borrow each other's sentences. The arm
    comparison ranks NETWORKS at DR-015's assumption point; the sweeps walk boxes
    around that point; this one holds the network fixed and moves a MEASURED
    resistance that no netlist in this repo had ever contained. What they share
    -- the DR-015 assumption table, the subset-corner justification, the
    environment block, the footer rules -- they share by calling the same
    helpers.
    """
    prov, lines, corner_ids, processes, temps, supplies = _open_corners_record(
        points, dut_netlist_text
    )

    rungs = [p for p in points if p["arm"] != CONTROL_ARM]
    control = next((p for p in points if p["arm"] == CONTROL_ARM), None)
    verdict = decap_esr_verdict(points, mults)

    a = lines.append
    a(
        "- **Claim**: `spec/target-spec.md#target-table` -- **Power** (DRAFT row), "
        "INFORMATIONAL only, and the evidence "
        "`spec/decision-records/DR-017-on-die-decoupling-budget.md`'s "
        "routing-parasitics open item (\"the sign of the net effect is still "
        "unmeasured\", issue #465) asks for. It edits no spec row, proposes no power "
        "target, and grades nothing against a ratified line. What it measures is "
        "whether the interconnect resistance the DRAWN decoupling ties add -- "
        "measured in `layout/sar-adc-top/`, never yet present in any netlist here -- "
        "raises or lowers the die-side rail excursion."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with "
        "THREE testbench-only transformations that are never written back to "
        "`design/`: the DUT's `GND` net is renamed `GND_DIE` (a net named `GND` is "
        "ngspice's global node 0 and would short out every series element this "
        "campaign inserts); the committed fragment's `VVDD`/`VVPWR`/`VVGND` source "
        "cards are re-pointed to board-side nodes; and on every rung above `0x`, "
        "each decoupling capacitor's two plate nodes are re-pointed behind a "
        "resistor carrying that tie's own MEASURED resistance. Source instance "
        "names, the `.tran` card, the clock/reset/input schedule and every code and "
        "phase `.meas` card are used verbatim, and the `0x` rung's deck contains "
        "none of the third transformation at all."
    )
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Ladder**: {len(mults)} rungs of the measured tie resistance "
        f"({', '.join(f'{m:g}x' for m in mults)}) plus the `{CONTROL_ARM}` control, "
        f"at {len(corner_ids)} corner point(s) = {len(points)} whole-ADC transients. "
        f"Every rung is the as-built `{DECAP_ESR_BASE_ARM}` topology with exactly "
        "those four resistors moved."
    )
    a(_stimulus_bullet())
    a("")

    a("## Why this record exists")
    a("")
    a(
        "[DR-017](../../../spec/decision-records/DR-017-on-die-decoupling-budget.md) "
        "put one `cap_mim_m3_1` pair per supply domain into the design, and its "
        "Amendment A argues about ESR on the strength of the DEVICE's own plate "
        "resistance (0.0235 Ohm for the shipped pair). Issue #440 then drew the ties "
        "and measured what the INTERCONNECT adds: about 590x that, and ~80 % of it "
        "single-cut vias. A 2x2 via array at each riser and each plate entry would "
        "cut it roughly 3x and is cheap in area -- but #440 declined to draw one, "
        "because the sign of the benefit is not obvious. At the as-built resistance "
        "the resonance the pair forms with DR-015's bond inductance has `Q ~ 1.06`, "
        "so the ties are comparable to the pair's own reactance there and are "
        "DAMPING that resonance; removing them raises `Q` as much as it lowers the "
        "impedance at resonance. Read the other way, ESR does not reach the pair's "
        "reactance until ~1.3 GHz, so the pair should already be "
        "reactance-dominated where the bounce lives. Both readings are design-time "
        "inferences about the same four resistors. This record replaces them with a "
        "measurement, and it is [issue "
        "#465](https://github.com/2AMLogic/sky130-sar-adc/issues/465). It supersedes "
        "nothing: the arm comparison ranks five networks at DR-015's assumption "
        "point, the sweeps walk boxes around it, and this ladder holds the network "
        "fixed and moves a resistance none of them contained."
    )
    a("")

    a("## The measured decoupling ties (issue #440)")
    a("")
    lines.extend(_decap_tie_table_lines(ties))
    a("")
    a(
        "**These are a measurement, not an assumption** -- unlike DR-015's R+L "
        "below. Their provenance is a committed, append-only layout record "
        f"(`{ties.record}`), and this runner reads the ohms out of that record's own "
        "`decap-ties.json` rather than carrying a copy, so a record here cannot "
        "state a resistance the layout never had. What they are NOT: an extraction. "
        "Each is one lumped DC resistor assembled from `build_layout.py`'s own "
        "geometry constants and the PDK's sheet/via resistances "
        "(`res_typical__cap_typical.spice`), with no frequency dependence, no skin "
        "effect, and **no interconnect inductance** -- that half of DR-017's "
        "routing-parasitics item needs `klt pex` and the device/net correspondence "
        "this flow does not yet have (klayout-tools#1878), and is out of scope here."
    )
    a("")

    a("## The package-style assumption (DR-015), which this ladder holds fixed")
    a("")
    lines.extend(_assumption_lines())
    a("")
    a(
        "Every row above is identical on every rung. The ladder moves only the four "
        "measured tie resistors, so the difference between two rungs is their own "
        "contribution and nothing else (DR-015 item 5). The `R_SUB` row does not "
        f"appear in this ladder's decks at all: the as-built `{DECAP_ESR_BASE_ARM}` "
        "topology bonds all four terminals, and only the `substrate`/`no-gnd-pad` "
        "arms carry that element."
    )
    a("")

    a("## The rungs, as networks")
    a("")
    lines.extend(
        arm_table_lines(
            [ARMS_BY_NAME[CONTROL_ARM]] + decap_esr_arms(tuple(mults), ties),
            substrate_note=False,
        )
    )
    a(
        f"The `{CONTROL_ARM}` row is the control every code delta below is taken "
        "against: ideal sources at the die, the zero-impedance case every other "
        "`sim/` campaign runs. Its own deck carries no tie resistors either -- the "
        "third transformation is applied per rung, and the control is not a rung. "
        f"Every rung carries the same lumped `R_SUBX = {R_SUBX_OHM:g} Ohm` between "
        "the analog and digital ground die nodes; in `ideal` both of its ends are "
        "held at 0 V, so it carries no current."
    )
    a("")

    a("## Die-side rail excursion per rung")
    a("")
    a(
        "| rung | tie resistance per domain | "
        + " | ".join(f"{name} pp (mV)" for name, _n, _l in RAIL_PROBES)
        + " |"
    )
    a("|---" * (len(RAIL_PROBES) + 2) + "|")
    for p in points:
        if p["arm"] == CONTROL_ARM:
            label, scale = f"`{CONTROL_ARM}` (control)", "-- (no bond, no ties)"
        else:
            mult = next(
                (m for m in mults if decap_esr_arm_name(m) == p["arm"]),
                None,
            )
            label = f"`{p['arm']}`"
            scale = "none" if mult in (None, 0.0) else ties.domain_esr_line(mult)
        cells = [_mv(p["extras"].get(f"{probe}_pp")) for probe, _n, _l in RAIL_PROBES]
        a(f"| {label} | {scale} | " + " | ".join(cells) + " |")
    a("")
    a(
        "`pp` is the peak-to-peak excursion of the DIE-side node over the same "
        "steady-state conversion the fragment averages its supply currents over. "
        f"The `{CONTROL_ARM}` row is the mechanical control: an ideal source holds "
        "each die node at its own DC value, so a nonzero ground excursion there "
        "would mean the networks are not wired the way this record says."
    )
    a("")

    a("## Captured code per rung")
    a("")
    lines.extend(_captured_code_table_lines(points, control, "rung"))
    a("")
    a(
        "The two `+-0.78*V_REF` columns are reported but EXCLUDED from the worst-delta "
        "column: `sim/full-conversion-transient/records/20260912-002315-9aaf1ca.md` "
        "already records them as wrong by ~100 LSB at every corner (issue #267, "
        "common-mode saturation at large differential input, still open), so a change "
        "there could not be attributed to a decoupling tie."
    )
    a("")

    a("## Average rail current per rung")
    a("")
    a(
        "| rung | I(VDD) (uA) | I(VPWR) (uA) | I(GND) (uA) | I(VREFP) (uA) | "
        "I(VCM) (uA) | total power (uW) |"
    )
    a("|---|---|---|---|---|---|---|")
    for p in points:
        a(f"| `{p['arm']}` | {_avg_current_cells(p)}")
    a("")

    a("## Findings")
    a("")
    for line in decap_esr_findings_lines(points, control, tuple(mults), ties):
        a(line)
    a("")

    a("## Wall-clock cost per run")
    a("")
    lines.extend(_wall_clock_table_lines(points, control, "rung"))
    a(
        "Reported for the same two reasons every record of this campaign reports it: "
        "it is the input to the subset-corner justification below, and it is itself a "
        "finding -- this campaign's expensive shape is the bonded one, and the "
        "`package` arm has repeatedly outrun a ~63-minute per-process budget on this "
        "fleet (issue #448), which is why this ladder has two rungs rather than four. "
        "These are wall-clock seconds on a shared, contended host, so they are ratios "
        "between rungs rather than a benchmark of either."
    )
    a("")

    a("## What this ladder does not cover")
    a("")
    a(
        "- **The interconnect INDUCTANCE of the same ties.** The other half of "
        "DR-017's routing-parasitics item. It needs an extraction (`klt pex`) that "
        "presumes a device/net correspondence this flow does not yet have "
        "(klayout-tools#1878, tracked with #103's LVS gap), so these decks model "
        "resistance only."
    )
    a(
        "- **The 2x2-via-array geometry itself.** This ladder brackets the reachable "
        "value between `0x` and the as-built `1x`; it does not run the projected "
        "~4-5 Ohm array ESR as its own rung. The arrays could never reach `0x` in "
        "any case -- they divide the via half of each ladder and leave the metal "
        f"half untouched. Of the analog return tie's {ties.tie_ohm['GND']:.3f} Ohm, "
        "issue #440 measured ~80 % as single via cuts; it is the met2 remainder of "
        "that -- not the whole tie -- that no via array can divide, and it is what "
        "holds even a fully arrayed tie above `0x`."
    )
    a(
        "- **Other corners.** One corner point, for the cost reason stated below. "
        "The full ratified grid at this ladder would be "
        f"{len(mults) + 1} x 9 whole-ADC transients."
    )
    a(
        "- **Board decoupling**, which no record of this campaign models, so every "
        "excursion here remains an upper bound rather than a prediction for a real "
        "system."
    )
    a(
        "- **The two near-full-scale inputs**, outside every code comparison above "
        "for the reason stated under that table (issue #267)."
    )
    a("")

    lines.extend(
        subset_corner_lines(
            corner_ids,
            "the decoupling-tie ESR ladder",
            f"the {len(points)} decks of this record",
            len(points),
            "a one-element sign measurement at the baseline corner",
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
                    f"{len(points)} ({len(rungs)} rungs + the `{CONTROL_ARM}` control "
                    f"x {len(corner_ids)} corner point)"
                ),
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "decoupling-tie measurement": (
                    f"{ties.record}/decap-ties.json -- {ties.domain_esr_line()} per "
                    f"domain, {ties.capacitance_f * 1e12:.3f} pF per domain (issue #440)"
                ),
                "tie-resistance ladder": (
                    "{" + ", ".join(f"{m:g}x" for m in mults) + "} of the measured value"
                ),
                "verdict": (
                    f"{verdict['direction']} at a +-{verdict['band'] * 100:g} % reading band"
                ),
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            decap_esr_invocation_line(tuple(mults), supersedes), supersedes
        )
    )

    # Deliberately NOT records/LATEST, for the same reason the two sweep writers
    # decline it: that pointer names the record this campaign's CITED claim rests
    # on -- the baseline-corner arm comparison DR-012 and
    # `docs/chipalooza/challenge-4-proposal.md`'s Power row cite, and which
    # DR-017's own erratum reads as "any undecoupled record" -- and this record
    # does not replace it. It asks a different question (which way a measured
    # interconnect resistance moves the rails), on a DUT body no other record in
    # this campaign has ever simulated. Moving the pointer would make citations
    # of the still-current arm-comparison record read as stale to the citation
    # gate while nothing had actually superseded them.
    return evidence.close_record(prov, lines, "Decoupling-tie ESR ladder record")

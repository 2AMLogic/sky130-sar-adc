"""The arm-comparison campaign: `run_supply_impedance.py`'s base campaign.

Issue #848's split of the runner. The five supply-return networks of
`common.ARMS` over a corner grid, plus this campaign's own record writer and
the findings/ablation prose only it emits. Imports `common` only.
"""
from __future__ import annotations

from pathlib import Path

from . import common
from .common import (
    ARMS,
    ARMS_BY_NAME,
    ARM_OMISSION_NOTES,
    BASELINE_CORNER,
    CONTROL_ARM,
    NOMINAL_SUPPLY_V,
    PACKAGE_L_H,
    PACKAGE_R_OHM,
    RAIL_PROBES,
    RUNNER_REL,
    R_SUBX_OHM,
    R_SUB_OHM,
    _assumption_lines,
    _avg_current_cells,
    _mv,
    _open_corners_record,
    _provenance_bullet,
    _stimulus_bullet,
    arm_table_lines,
    code_delta,
    full_ratified_grid,
    subset_corner_lines,
    tb,
    worst_mid_scale_delta,
)
from harness import corners as corners_mod, evidence


# --------------------------------------------------------------------------
# The arm comparison's own record
# --------------------------------------------------------------------------
def invocation_line(
    arm_names: list[str],
    corners_mode: bool,
    supersedes: str,
    corner_points: list[str] | None = None,
) -> str:
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
    if corner_points:
        parts.append("--corner-points " + ",".join(corner_points))
    elif corners_mode:
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
    corner_points: list[str] | None = None,
) -> Path:
    prov, lines, corner_ids, processes, temps, supplies = _open_corners_record(
        points, dut_netlist_text
    )

    arms_run = [name for name in (a.name for a in ARMS) if any(p["arm"] == name for p in points)]
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
    a(_provenance_bullet(" on the arms that bond them through an impedance"))
    a(corners_mod.corner_matrix_summary_line(processes, temps, supplies, len(corner_ids)))
    a(
        f"- **Arms**: {len(arms_run)} supply-return networks "
        + ", ".join(f"`{name}`" for name in arms_run)
        + f" x {len(corner_ids)} corner point(s) = {len(points)} transient runs. "
        f"`{CONTROL_ARM}` is the control: it is exactly what every existing "
        "`sim/` campaign runs today."
    )
    a(_stimulus_bullet())
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
            a(f"| `{cid}` | `{name}` | {_avg_current_cells(p)}")
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

    # Keyed on what was actually COVERED, not on which flag asked for it: a
    # `--corner-points` run is a subset of the ratified grid and owes the same
    # justification a baseline-only run does (issue #409 item 1). Only a run
    # that covered all nine points is exempt.
    if len(corner_ids) < len(full_ratified_grid()):
        lines.extend(
            subset_corner_lines(
                corner_ids,
                "the arm comparison",
                f"{len(arms_run)} arms",
                len(arms_run),
                (
                    "a mechanism comparison over the corner points it names"
                    if len(corner_ids) > 1
                    else "a mechanism comparison at the baseline corner"
                ),
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
        evidence.footer_lines(
            invocation_line(arm_names, corners_mode, supersedes, corner_points), supersedes
        )
    )

    path = evidence.close_record(prov, lines, "Record")
    # The pointer names the record this campaign's CITED claim rests on -- the
    # baseline-corner arm comparison DR-012 and
    # `docs/chipalooza/challenge-4-proposal.md`'s Power row cite by id -- and
    # moving it is what makes every citing document stale (the citation gate's
    # checks 3 and 4). A corner-axis record does not supersede that claim: it
    # asks the follow-up question "does the corner axis move it?", on a reduced
    # arm set, and the arms it drops are where the bond-inductance ablation and
    # the substrate arm live. So it mints and does not repoint, the same
    # disposition -- and for the same reason -- as the `--sweep` and
    # `--null-sweep` writers. Whether a FULL nine-point grid at the full arm
    # set should take the pointer is a decision for that record and for the
    # documents citing it, not something this writer makes silently.
    if corner_ids == [corners_mod.corner_id(*BASELINE_CORNER)]:
        evidence.write_latest_pointer(common.EXPERIMENT_DIR, prov.record_id)
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

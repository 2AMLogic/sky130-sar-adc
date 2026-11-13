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

THE DECOUPLING-TIE ESR LADDER (`--decap-esr`, issue #465). Every arm above
takes the committed `design/sar_adc_top.spice` verbatim, and since DR-017 that
netlist ties each supply domain's own MiM decoupling pair to its rails through
IDEAL wires. The drawn layout does not: issue #440's `probe-decap-sites.py`
measured the four drawn ties at 13.837 Ohm (analog) and 13.448 Ohm (digital)
per domain, ~80 % of it single-cut vias. No netlist in this repo has ever
carried that resistance, so every decoupled record this campaign has minted so
far measures a capacitor pair that is better connected than the one on the
die. `--decap-esr` is the ladder that closes that gap: the as-built `package`
topology, re-run with the MEASURED per-domain tie resistance in series with
each MiM pair, over a bounded multiplier ladder whose `0x` rung is the
committed netlist card for card. See `DECAP_ESR_*` below.

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
import os
import sys
import tempfile
from pathlib import Path

from supply_impedance_campaigns import common
from supply_impedance_campaigns.arm_comparison import (
    findings_lines,
    write_record,
)
from supply_impedance_campaigns.common import (
    ARMS,
    ARMS_BY_NAME,
    CONTROL_ARM,
    DECAP_TIE_RECORD,
    PACKAGE_L_H,
    REPO_ROOT,
    R_SUBX_OHM,
    SWEEP_BASE_ARM,
    check_pdk_has_no_bare_gnd_node,
    cost_probe_lines,
    fragment_tran_stop_ns,
    patch_dut_decap_ties,
    patch_dut_ground,
    resolve_grid,
    run_campaign,
    run_cost_probe,
    tb,
)
from supply_impedance_campaigns.decap_esr import (
    DECAP_ESR_BASE_ARM,
    DECAP_ESR_MULTIPLIERS,
    DecapTieMeasurement,
    decap_esr_anchor_matches_base_arm,
    decap_esr_arm_name,
    decap_esr_arms,
    decap_esr_findings_lines,
    load_decap_ties,
    write_decap_esr_record,
)
from supply_impedance_campaigns.midscale_probe import (
    MIDSCALE_PROBE_CORNER,
    MIDSCALE_PROBE_REFERENCE_RECORD,
    MIDSCALE_PROBE_VARIANTS,
    PERTURBATIONS,
    PERTURBATIONS_BY_NAME,
    midscale_probe_findings_lines,
    run_midscale_probe,
    write_midscale_probe_record,
)
from supply_impedance_campaigns.null_sweep import (
    NULL_SWEEP_BASE_ARM,
    NULL_SWEEP_RSUBX_OHM,
    null_sweep_anchor_matches_base_arm,
    null_sweep_arm_name,
    null_sweep_arms,
    null_sweep_findings_lines,
    write_null_sweep_record,
)
from supply_impedance_campaigns.sweep import (
    SWEEP_L_MULTIPLIERS,
    SWEEP_RSUBX_OHM,
    sweep_anchor_matches_base_arm,
    sweep_arm_name,
    sweep_arms,
    sweep_findings_lines,
    write_sweep_record,
)
from harness import corners as corners_mod, pdk, toolchain
import run_conversion as fc


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
        "the baseline corner only. Hours of sequential whole-ADC transients -- see "
        "this experiment's README.md, and --corner-points for advancing the same "
        "grid in session-sized pieces",
    )
    ap.add_argument(
        "--corner-points",
        default=None,
        metavar="ID,ID,...",
        help="run a NAMED SUBSET of the same ratified OAT grid, by corner-id (e.g. "
        "tt_27c_1.80v,ss_27c_1.80v). Narrows the ratified set; it cannot name a "
        "point outside it. Exists because the full grid is hours and a dispatch "
        "session is not (issue #409 item 1): with --log-cache, finished points "
        "carry across sessions, so the grid is completed by accumulation. The "
        "record states its own subset-corner justification either way. Mutually "
        "exclusive with --corners.",
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
        "--midscale-probe",
        action="store_true",
        help="issue #455: instead of the arm comparison, run the mid-scale boundary "
        "probe -- a DIAGNOSTIC at one corner (default "
        f"{corners_mod.corner_id(*MIDSCALE_PROBE_CORNER)}, the point the 6-LSB "
        "mid-scale move was recorded at) that (a) re-runs the committed decks of that "
        "point and its control and diffs them against the committed logs, and (b) "
        "re-runs the control under supply-UNRELATED perturbations (a +-0.1 LSB DC "
        "input offset, a halved .tran step), with per-bit-trial comparator-margin "
        "probes on every variant. Writes its own record with --record; that record "
        "supersedes nothing and does not move records/LATEST.",
    )
    ap.add_argument(
        "--midscale-probe-variants",
        default=",".join(MIDSCALE_PROBE_VARIANTS),
        metavar="ARM:PERT,...",
        help="the probe's variant list, as `arm:perturbation` pairs (default: "
        + ",".join(MIDSCALE_PROBE_VARIANTS)
        + "). Perturbations available: "
        + ", ".join(p.name for p in PERTURBATIONS)
        + ". A departure from the default list is stated in the record's own footer.",
    )
    ap.add_argument(
        "--decap-esr",
        action="store_true",
        help="DR-017's routing-parasitics open item (issue #465): instead of the "
        "named arms, run a bounded ONE-element ladder over the MEASURED "
        "decoupling-tie interconnect resistance -- the as-built `"
        + DECAP_ESR_BASE_ARM
        + "` topology with each domain's own drawn tie resistance (from "
        f"{DECAP_TIE_RECORD}/decap-ties.json, issue #440) in series with that "
        "domain's MiM pair -- at the baseline corner, plus the `" + CONTROL_ARM + "` "
        "control. The `0x` rung is the committed netlist card for card, so the "
        "difference between rungs is those four resistors' own contribution. Writes "
        "its own record with --record; that record supersedes nothing and does not "
        "move records/LATEST.",
    )
    ap.add_argument(
        "--decap-esr-mult",
        default=",".join(f"{m:g}" for m in DECAP_ESR_MULTIPLIERS),
        metavar="M1,M2,...",
        help="the decoupling-tie ladder, as multipliers of the MEASURED per-tie "
        f"resistance (default: {','.join(f'{m:g}' for m in DECAP_ESR_MULTIPLIERS)}). "
        "`0` is the committed netlist (no tie resistance at all) and must be present "
        "-- it is the rung that anchors the ladder to the campaign's existing "
        "decoupled records. A departure from the default ladder is stated in the "
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

    corner_points = [cid.strip() for cid in (args.corner_points or "").split(",") if cid.strip()]
    if corner_points and args.corners:
        print(
            "FAIL: --corners and --corner-points are the same axis stated two ways "
            "(all nine ratified points, or a named subset of them). Pick one.",
            file=sys.stderr,
        )
        return 2
    try:
        grid = resolve_grid(args.corners, corner_points)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    # Ratified-grid order, so the footer names the subset the same way the
    # record's tables order it however the caller typed the list.
    corner_points = [corners_mod.corner_id(*point) for point in grid] if corner_points else []

    l_mults: tuple[float, ...] = ()
    rsubx_values: tuple[float, ...] = ()
    null_rsub_values: tuple[float, ...] = ()
    decap_mults: tuple[float, ...] = ()
    decap_ties: DecapTieMeasurement | None = None
    modes = [
        name
        for name, on in (
            ("--sweep", args.sweep),
            ("--null-sweep", args.null_sweep),
            ("--midscale-probe", args.midscale_probe),
            ("--decap-esr", args.decap_esr),
        )
        if on
    ]
    # The `--sweep` + `--null-sweep` pair keeps its own, older message below;
    # this guard covers every pairing that involves the decap-ESR ladder.
    if args.decap_esr and len(modes) > 1:
        print(
            f"FAIL: {' and '.join(modes)} are different experiments (two topologies "
            "and a netlist transformation) and each writes its own record. Run them "
            "one at a time.",
            file=sys.stderr,
        )
        return 2
    if args.decap_esr:
        if args.arms is not None:
            print(
                "FAIL: --arms is not meaningful with --decap-esr. The ladder "
                f"synthesizes its own rungs over the `{DECAP_ESR_BASE_ARM}` topology "
                f"and always runs the `{CONTROL_ARM}` control; pick the ladder with "
                "--decap-esr-mult instead.",
                file=sys.stderr,
            )
            return 2
        if args.corners or args.corner_points:
            print(
                "FAIL: --decap-esr with --corners/--corner-points is refused, for the "
                "same reason --sweep is: it multiplies a ladder of the campaign's "
                "most expensive arm shape by the ratified grid, which is a campaign in "
                "its own right rather than a longer version of this one -- see this "
                "experiment's README.md.",
                file=sys.stderr,
            )
            return 2
        try:
            decap_mults = tuple(float(v) for v in args.decap_esr_mult.split(",") if v.strip())
        except ValueError as exc:
            print(f"FAIL: could not parse the decap-ESR ladder: {exc}", file=sys.stderr)
            return 2
        if not decap_mults:
            print("FAIL: the decap-ESR ladder needs at least one rung", file=sys.stderr)
            return 2
        if 0.0 not in decap_mults:
            print(
                "FAIL: the decap-ESR ladder must include the `0` rung -- it is the "
                "committed netlist card for card, and it is what ties this record's "
                "numbers to the campaign's existing decoupled records. Without it "
                "the ladder measures a resistance against nothing.",
                file=sys.stderr,
            )
            return 2
        try:
            decap_ties = load_decap_ties()
            ladder = decap_esr_arms(decap_mults, decap_ties)
            # Dry-run the DUT transformation now rather than after the first
            # hour: a netlist whose decoupling cards moved would otherwise fail
            # part-way through the ladder.
            body, _hits = patch_dut_ground(fc.dut_text())
            for arm in ladder:
                patch_dut_decap_ties(body, arm)
        except RuntimeError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        if not decap_esr_anchor_matches_base_arm(decap_ties):
            print(
                "FAIL: the decap-ESR ladder's `0x` rung is no longer card-for-card "
                f"the `{DECAP_ESR_BASE_ARM}` arm on the committed netlist -- the "
                "ladder would not be a one-element walk away from what this campaign "
                "has already recorded. Re-derive it before running.",
                file=sys.stderr,
            )
            return 2
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
        if args.corners or args.corner_points:
            print(
                "FAIL: --null-sweep with --corners/--corner-points is refused, for "
                "the same reason --sweep is: it multiplies a swept ladder by the "
                "ratified grid, which is a campaign in its own right rather than a "
                "longer version of this one -- see this experiment's README.md.",
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
        if args.corners or args.corner_points:
            print(
                "FAIL: --sweep with --corners/--corner-points is refused. It is two "
                "of issue #409's costs multiplied together (a 2-D box at every "
                "ratified corner) -- nine boxes of whole-ADC transients, a campaign "
                "in its own right rather than a longer version of this one. See this "
                "experiment's README.md.",
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

    probe_variants: tuple[str, ...] = ()
    probe_corner = MIDSCALE_PROBE_CORNER
    if args.midscale_probe:
        if args.sweep or args.null_sweep or args.cost_probe is not None:
            print(
                "FAIL: --midscale-probe is a diagnostic about this campaign's own "
                "code comparison, not a swept network box or a cost probe. Each "
                "writes its own record; run them one at a time.",
                file=sys.stderr,
            )
            return 2
        if args.arms is not None:
            print(
                "FAIL: --arms is not meaningful with --midscale-probe: the probe "
                "names its own (arm, perturbation) variants. Use "
                "--midscale-probe-variants instead.",
                file=sys.stderr,
            )
            return 2
        if args.corners:
            print(
                "FAIL: --midscale-probe --corners is refused. The probe is a "
                "mechanism trace at the ONE point the anomaly was recorded at; the "
                "ratified grid's mid-scale codes are already recorded (see "
                f"records/{MIDSCALE_PROBE_REFERENCE_RECORD}.md), and this probe "
                "exists to say what they mean. Name a different single point with "
                "--corner-points if needed.",
                file=sys.stderr,
            )
            return 2
        if len(grid) != 1:
            print(
                f"FAIL: --midscale-probe runs at exactly one corner point, got "
                f"{len(grid)}. Pass a single --corner-points id, or none for the "
                f"default {corners_mod.corner_id(*MIDSCALE_PROBE_CORNER)}.",
                file=sys.stderr,
            )
            return 2
        probe_corner = (
            grid[0] if corner_points else MIDSCALE_PROBE_CORNER
        )
        probe_variants = tuple(
            v.strip() for v in args.midscale_probe_variants.split(",") if v.strip()
        )
        if not probe_variants:
            print("FAIL: --midscale-probe-variants needs at least one variant", file=sys.stderr)
            return 2
        for spec in probe_variants:
            arm_name, sep, pert_name = spec.partition(":")
            if not sep or arm_name not in ARMS_BY_NAME or pert_name not in PERTURBATIONS_BY_NAME:
                print(
                    f"FAIL: unknown probe variant {spec!r}. Expected `arm:perturbation` "
                    f"with arm in {[a.name for a in ARMS]} and perturbation in "
                    f"{[p.name for p in PERTURBATIONS]}.",
                    file=sys.stderr,
                )
                return 2
        if f"{CONTROL_ARM}:as-committed" not in probe_variants:
            print(
                f"FAIL: the probe's variant list must include `{CONTROL_ARM}:"
                "as-committed`. It is the reproduction control: without it there is "
                "nothing to say whether this host reproduces the recorded point at "
                "all, and every perturbation row would be a delta against nothing.",
                file=sys.stderr,
            )
            return 2

    if args.cost_probe is not None:
        if not (args.sweep or args.null_sweep or args.decap_esr):
            print(
                "FAIL: --cost-probe prices a synthesized box or ladder; pass "
                "--sweep, --null-sweep or --decap-esr too. The named arms already have "
                "measured per-run wall clock in the campaign's arm-comparison records.",
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
        common.EXPERIMENT_DIR / "records" / f"{args.supersedes}.md"
    ).is_file():
        print(
            f"FAIL: --supersedes {args.supersedes}: no such record under "
            f"{os.path.relpath(common.EXPERIMENT_DIR / 'records', REPO_ROOT)}/",
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
    gate = toolchain.preflight(check)
    if gate is not None:
        return gate

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
            if args.decap_esr:
                assert decap_ties is not None
                probe_arms = [ARMS_BY_NAME[CONTROL_ARM]] + decap_esr_arms(
                    decap_mults, decap_ties
                )
                anchor_name = decap_esr_arm_name(0.0)
                what = "decoupling-tie ESR ladder"
            elif args.null_sweep:
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

        if args.midscale_probe:
            print(
                f"Running the mid-scale boundary probe (issue #455) at "
                f"{corners_mod.corner_id(*probe_corner)}: {len(probe_variants)} "
                "full-conversion transients, one at a time "
                f"({', '.join(probe_variants)}):"
            )
            points, dut_netlist_text = run_midscale_probe(
                probe_variants, probe_corner, scratch, args.quiet, log_cache=log_cache
            )
            print("")
            for line in midscale_probe_findings_lines(points):
                print(line)
            if args.record:
                write_midscale_probe_record(
                    points, dut_netlist_text, probe_variants, args.supersedes
                )
            return 1 if any(p["missing"] for p in points) else 0

        if args.decap_esr:
            assert decap_ties is not None
            # The control runs first (every code delta is taken against it) and
            # the ladder ascends, so an interrupted run leaves the rung that
            # anchors this record to the existing decoupled records on disk.
            arms = [ARMS_BY_NAME[CONTROL_ARM]] + decap_esr_arms(decap_mults, decap_ties)
            print(
                "Running the bounded decoupling-tie ESR ladder at the baseline "
                f"corner: {len(decap_mults)} rungs "
                f"({', '.join(f'{m:g}x' for m in decap_mults)} of "
                f"{decap_ties.domain_esr_line()} per domain, measured in "
                f"{decap_ties.record}) + the `{CONTROL_ARM}` control = {len(arms)} "
                "full-conversion transients:"
            )
        elif args.null_sweep:
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
            print(
                f"Running {len(arms)} arm(s) x {len(grid)} corner point(s) = "
                f"{len(arms) * len(grid)} full-conversion transients"
                + (
                    " (" + ", ".join(corners_mod.corner_id(*p) for p in grid) + ")"
                    if corner_points
                    else ""
                )
                + ":"
            )

        points, dut_netlist_text = run_campaign(
            arms, grid, args.quiet, scratch, log_cache=log_cache
        )

        print("")
        if args.decap_esr:
            assert decap_ties is not None
            control = next((p for p in points if p["arm"] == CONTROL_ARM), None)
            for line in decap_esr_findings_lines(points, control, decap_mults, decap_ties):
                print(line)
            if args.record:
                write_decap_esr_record(
                    points, dut_netlist_text, decap_mults, decap_ties, args.supersedes
                )
        elif args.null_sweep:
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
                write_record(
                    points,
                    dut_netlist_text,
                    args.corners,
                    arm_names,
                    args.supersedes,
                    corner_points,
                )

    return 1 if any(p["missing"] for p in points) else 0


if __name__ == "__main__":
    raise SystemExit(main())

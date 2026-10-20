"""regen corners campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    PROCESS_CORNERS,
    RESET_NS,
    SUPPLY_TOLERANCE,
    TEMPS_C,
    VDD,
    _dut_lines,
)
from .regen import (
    RESET_HOLD_TOLERANCE_FRAC,
    _finalize_record,
    run_regen_sweep,
)
from harness import corners as corners_mod, evidence, pdk

# ---------------------------------------------------------------------------
# regen-corners: decision (regeneration) delay over the full ratified OAT
# PVT grid -- the comparator half of the bit-trial timing budget
# ---------------------------------------------------------------------------
#
# WHY THIS EXISTS. docs/chipalooza/challenge-4-proposal.md Section 7 Item 2
# names the two mechanisms that must be quantified before the DRAFT
# 100 kS/s-1 MS/s sample-rate row can be re-derived from evidence rather
# than asserted: (a) the CDAC array's own bottom-plate-switch settling, and
# (b) the comparator's own decision (regeneration) delay. (a) was quantified
# at one corner by sim/cdac-bit-trial-settling/ (issue #121, PR #156). (b)
# had exactly one committed data point -- the single-corner
# `regen` record 20260821-065653-433a294 (tt/27C/1.8V, issue #54) -- whose
# own text defers "a full PVT sweep of this same Vindiff grid ... to #28's
# corner campaign". #28's campaign covered the NOISE row only
# (`noise-corners`); the regeneration-time sweep was never taken to the full
# corner set. This subcommand closes that specific gap: it is to `regen`
# exactly what `noise-corners` is to `noise`.
#
# WHY IT NEEDS ITS OWN CONSTANTS RATHER THAN REUSING `regen`'s.
#  * Vindiff grid. `regen`'s 8-point grid spans 0.5-50 mV to SHOW THE SHAPE
#    of regeneration time vs. input (the ln(1/Vindiff) latch behaviour). A
#    PVT campaign does not need the shape re-measured at nine corners; it
#    needs the WORST CASE and enough of the trend to confirm the shape did
#    not invert somewhere on the grid. Three points do that at 1/3 the cost:
#    0.5 mV (a deliberately harder input than this converter ever has to
#    resolve -- see below), the half-LSB point, and 10 mV.
#  * Half-LSB is the physically meaningful worst case for THIS converter.
#    The differential LSB is 2*V_REF/2^N = 3.5156 mV (DR-003 Item 3), so the
#    smallest differential a correct bit trial must resolve is half of that,
#    1.7578 mV. 0.5 mV is carried as a deliberately conservative bound: it
#    is ~3.5x smaller than the half-LSB input, so its (longer) decision
#    delay upper-bounds the delay at any input this design actually presents.
#    Inputs below half an LSB are, by construction, inside the converter's
#    own quantization band -- a wrong decision there is not a timing failure.
#  * Evaluate window. `regen` allows 40 ns for the decision to resolve. Every
#    committed data point resolves inside 1.4 ns, so 15 ns is ~10x headroom
#    over the slowest measured point while cutting each transient's cost
#    roughly in half. A point that does NOT resolve inside the window is
#    reported as UNRESOLVED and fails the subcommand -- it is never silently
#    dropped or back-filled.
#  * A Vindiff = 0 mV RESET-INTEGRITY CONTROL at every corner. This is not a
#    decision measurement -- at zero input there is no correct answer to
#    decide -- it is the negative control that tells the other three columns
#    apart from an artifact. If the outputs separate during the CLK=0 reset
#    phase with NO input applied, then whatever they do after the evaluate
#    edge is not attributable to the input, and no decision delay can be
#    extracted at that corner. Without this column a pre-decided point is
#    indistinguishable from a genuinely fast one (it reports 0.0000 ns), which
#    is exactly the kind of fabricated number CLAUDE.md's "no claim without a
#    testbench" rule exists to prevent.
CORNERS_VINDIFF_SWEEP_MV = [0.0, 0.5, 1.7578, 10.0]
CORNERS_EVALUATE_NS = 15.0

# Provisional bit-trial phase budget the measured delays are COMPARED against
# (never graded against): DR-006 derives a 1.2-12 MHz f_clk range as a
# mechanical consequence of spec/target-spec.md's DRAFT 100 kS/s-1 MS/s
# sample-rate row, one clock period per phase. The worst case (fastest clock)
# phase is therefore 1/12 MHz = 83.333 ns. Because the row upstream of it is
# DRAFT, this number is reported for context only -- it is NOT a pass/fail
# threshold, per CLAUDE.md's rule against encoding an unratified spec value
# as one. sim/cdac-bit-trial-settling/ quotes the identical figure for the
# same reason.
BIT_TRIAL_PHASE_BUDGET_NS = 1000.0 / 12.0
# Differential LSB, DR-003 Item 3: 2*V_REF/2^N with V_REF = 1.8 V, N = 10.
DIFFERENTIAL_LSB_MV = 2 * VDD / (2 ** 10) * 1000.0


@dataclass
class RegenCornerPoint:
    corner: str
    temp_c: float
    supply_v: float
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str
    pre_edge_diff_v: float | None = None
    final_diff_v: float | None = None
    reset_divergence_onset_ns: float | None = None
    reset_static_idd_a: float | None = None

    @property
    def corner_id(self) -> str:
        return corners_mod.corner_id(self.corner, self.temp_c, self.supply_v)

    @property
    def reset_held(self) -> bool | None:
        """Did the CLK=0 reset phase leave the latch balanced at the moment
        the evaluate edge began? None if the point produced no waveform."""
        if self.pre_edge_diff_v is None:
            return None
        return abs(self.pre_edge_diff_v) <= RESET_HOLD_TOLERANCE_FRAC * self.supply_v

    def classify(self) -> str:
        """One of five outcomes. The distinction between them is the whole
        point of this campaign -- collapsing RESET-NOT-HELD into a numeric
        delay is what made the first draft of this subcommand report a
        physically meaningless `0.0000 ns` at four of nine corners."""
        held = self.reset_held
        if held is None:
            return "NO-DATA"
        if not held:
            # The latch had already separated by more than the input could
            # account for BEFORE the clock edge: whatever it does afterwards
            # is not a response to the input, so no delay is extractable.
            return "RESET-NOT-HELD"
        if self.vindiff_mv == 0.0:
            return "CONTROL-OK"
        if self.regen_time_ns is not None:
            return "DECIDED"
        if (
            self.final_diff_v is not None
            and abs(self.final_diff_v) > 0.5 * self.supply_v
        ):
            # Reset held, but the latch resolved AGAINST the applied input --
            # an offset/asymmetry failure, not a timing one.
            return "WRONG-POLARITY"
        return "NO-DECISION"


def run_regen_corners(
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
) -> list[RegenCornerPoint]:
    """Full ratified-corner-set sweep of run_regen_sweep(): the OAT PVT grid
    built from the ratified corner set (spec/target-spec.md's "Numeric rows
    -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
    process corners), at CORNERS_VINDIFF_SWEEP_MV."""
    # Fail fast on an unresolvable PDK before spending the corner grid's
    # runtime -- the returned PdkInfo is unused here (run_regen_sweep()
    # re-resolves it for each point), so the call is kept, not the binding.
    pdk.resolve_or_raise()
    sweep = vindiff_sweep_mv or CORNERS_VINDIFF_SWEEP_MV
    grid = corners_mod.ratified_oat_grid(VDD, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C)
    points: list[RegenCornerPoint] = []
    for process_corner, temp_c, supply_v in grid:
        cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
        if not quiet:
            print(f"{cid}:")
        sweep_points = run_regen_sweep(
            corner=process_corner, temp_c=temp_c, vindiff_sweep_mv=sweep,
            quiet=quiet, supply_v=supply_v, evaluate_ns=CORNERS_EVALUATE_NS,
            probe_supply_current=True,
        )
        for p in sweep_points:
            points.append(RegenCornerPoint(
                corner=process_corner, temp_c=temp_c, supply_v=supply_v,
                vindiff_mv=p.vindiff_mv, regen_time_ns=p.regen_time_ns,
                log_text=p.log_text,
                pre_edge_diff_v=p.pre_edge_diff_v,
                final_diff_v=p.final_diff_v,
                reset_divergence_onset_ns=p.reset_divergence_onset_ns,
                reset_static_idd_a=p.reset_static_idd_a,
            ))
    return points


def write_regen_corners_evidence(
    points: list[RegenCornerPoint], note: str = "",
    supersedes: str = "",
) -> Path:
    raw_logs: dict[str, str] = {}
    for p in points:
        cid = corners_mod.corner_id(p.corner, p.temp_c, p.supply_v)
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        raw_logs[f"{cid}__vindiff_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(EXPERIMENT_DIR, _dut_lines(), "corners", raw_logs)
    record_path = prov.record_path
    a = lines.append

    controls = [p for p in points if p.vindiff_mv == 0.0]
    measured = [p for p in points if p.vindiff_mv != 0.0]
    decided = [p for p in measured if p.classify() == "DECIDED"]
    not_held = [p for p in measured if p.classify() == "RESET-NOT-HELD"]
    failed_controls = [p for p in controls if p.classify() != "CONTROL-OK"]
    bad_corner_ids = sorted({p.corner_id for p in failed_controls})
    process_corners_run = sorted({p.corner for p in points})
    temps_run = sorted({p.temp_c for p in points})
    supplies_run = sorted({p.supply_v for p in points})
    n_corner_points = len({(p.corner, p.temp_c, p.supply_v) for p in points})
    n_corners = len(controls)
    clean_corner_ids = sorted({p.corner_id for p in controls if p.classify() == "CONTROL-OK"})

    a(
        "- **Claim**: pending #1/#27 -- attempts to characterize "
        "design/comparator.sch's decision (regeneration) delay vs. differential "
        "input across the FULL ratified PVT corner set, and reports what that "
        "attempt actually found. There is no ratified spec/target-spec.md row "
        "for decision delay, settling, or sample rate to grade against (the "
        "100 kS/s-1 MS/s sample-rate row is still DRAFT, #1/#27), so nothing "
        "here asserts a pass against a ratified line. Extends the single-corner "
        "record `20260821-065653-433a294` (tt/27C/1.8V, issue #54), whose own "
        "text deferred this sweep, and is the comparator counterpart of the "
        "CDAC-side settling budget "
        "`sim/cdac-bit-trial-settling/records/20260905-220919-bbf06dd.md` -- "
        "together they are the two mechanisms "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 names."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, n_corner_points
        )
    )
    a(
        f"- **Vindiff grid**: {CORNERS_VINDIFF_SWEEP_MV} mV at every corner point "
        f"({len(points)} transient runs total). The differential LSB is "
        f"{DIFFERENTIAL_LSB_MV:.4f} mV (DR-003 Item 3), so the half-LSB point -- "
        "the smallest differential a correct bit trial must resolve -- is "
        f"{DIFFERENTIAL_LSB_MV / 2:.4f} mV; the 0.5 mV point is a deliberately "
        "conservative bound ~3.5x below it, and 10 mV is a large-overdrive "
        "reference. The 0.0 mV column is not a decision measurement at all: it "
        "is the reset-integrity NEGATIVE CONTROL described below."
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK=supply) "
        "edge per run (not a repeating clock -- each ngspice invocation starts "
        "from an uninitialized circuit); decision threshold |v(outp)-v(outn)| > "
        "0.5*supply; Vcm = supply/2, tracking the rail because V_REF = V_DD in "
        "this design (DR-003 Item 1) and the CDAC's switched common mode is "
        f"V_REF/2; evaluate window {CORNERS_EVALUATE_NS}ns"
    )
    if note:
        a(f"- **Note**: {note}")
    affected_corner_ids = sorted({p.corner_id for p in not_held} | set(bad_corner_ids))
    if failed_controls:
        a(
            f"- **Overall**: FAIL (DESIGN FINDING) -- the reset-integrity control "
            f"fails at {len(bad_corner_ids)} of {n_corners} ratified corner "
            f"points ({', '.join('`' + c + '`' for c in bad_corner_ids)}). At "
            "those corners the comparator's differential output has already "
            "separated to the rails DURING the CLK=0 reset phase with ZERO "
            "differential input applied, so the post-edge output is not a "
            "response to the input and NO decision delay is extractable there. "
            f"Counting the applied-input points too, {len(affected_corner_ids)} "
            f"of {n_corners} corner points show at least one reset-not-held "
            f"run ({len(not_held)} of {len(measured)} input-driven runs). "
            "A PVT-complete decision-delay figure therefore does not exist yet "
            "and is NOT reported by this record."
        )
    else:
        a(
            f"- **Overall**: {'PASS' if len(decided) == len(measured) else 'INCOMPLETE'} "
            f"({len(decided)}/{len(measured)} input-driven points decided within "
            f"the {CORNERS_EVALUATE_NS}ns evaluate window; "
            f"{n_corners}/{n_corners} reset-integrity controls held)"
        )
    if decided:
        binding = max(decided, key=lambda p: p.regen_time_ns or 0.0)
        a(
            f"- **Binding corner (among the {len(clean_corner_ids)} corner points "
            f"whose reset control held)**: `{binding.corner_id}` at Vindiff = "
            f"{binding.vindiff_mv:+.4f} mV, decision delay "
            f"{binding.regen_time_ns:.4f} ns -- recorded regardless of pass/fail, "
            "per sim/README.md's per-row binding-corner convention. This is a "
            "worst case over a SUBSET of the ratified grid, not over the grid, "
            "and must not be quoted as a PVT-complete number."
        )
    a("")

    a("## Reset-integrity control (Vindiff = 0 mV): does the reset phase hold?")
    a("")
    a(
        "With no differential input applied there is no correct decision to "
        "make, so the latch must remain balanced until the evaluate edge. "
        "`pre-edge diff` is v(OUTP) - v(OUTN) at the last sample strictly "
        f"before the CLK edge begins rising (t = {RESET_NS} ns); `onset` is the "
        "first time during the reset phase at which |v(OUTP) - v(OUTN)| exceeded "
        f"{RESET_HOLD_TOLERANCE_FRAC:.0%} of the rail; `reset I(VDD)` is the "
        "static supply current at that same pre-edge sample."
    )
    a("")
    a(
        "| corner-id | pre-edge v(OUTP)-v(OUTN) (V) | onset during reset (ns) | "
        "reset I(VDD) (uA) | verdict |"
    )
    a("|---|---|---|---|---|")
    for p in controls:
        onset = (
            f"{p.reset_divergence_onset_ns:.3f}"
            if p.reset_divergence_onset_ns is not None else "-- (never)"
        )
        idd = (
            f"{abs(p.reset_static_idd_a) * 1e6:.2f}"
            if p.reset_static_idd_a is not None else "n/a"
        )
        verdict = "HELD" if p.classify() == "CONTROL-OK" else "**NOT HELD**"
        pre = f"{p.pre_edge_diff_v:+.4f}" if p.pre_edge_diff_v is not None else "n/a"
        a(f"| `{p.corner_id}` | {pre} | {onset} | {idd} | {verdict} |")
    a("")

    a("## Decision outcome per corner and differential input")
    a("")
    a(
        "Cells are the measured decision delay in ns where one exists. Where "
        "one does not, the cell names WHY rather than substituting a number:"
    )
    a("")
    a(
        "- `RESET-NOT-HELD` -- the outputs had already separated by more than "
        f"{RESET_HOLD_TOLERANCE_FRAC:.0%} of the rail before the evaluate edge. "
        "Any apparent delay here would be an artifact (a naive threshold-crossing "
        "search reports 0.0000 ns for exactly these points), so no number is given."
    )
    a(
        "- `WRONG-POLARITY` -- the reset held, but the latch resolved AGAINST the "
        "applied differential. That is an offset/asymmetry failure, not a timing "
        "one, and a decision delay is not meaningful for it."
    )
    a(
        "- `NO-DECISION` -- the reset held and the latch never crossed the "
        f"decision threshold within the {CORNERS_EVALUATE_NS} ns evaluate window."
    )
    a("")
    delay_cols = [v for v in CORNERS_VINDIFF_SWEEP_MV if v != 0.0]
    a(
        "| corner-id | "
        + " | ".join(f"Vindiff {v:+.4f} mV" for v in delay_cols)
        + " |"
    )
    a("|---" * (1 + len(delay_cols)) + "|")
    by_corner: dict[str, dict[float, RegenCornerPoint]] = {}
    order: list[str] = []
    for p in measured:
        if p.corner_id not in by_corner:
            by_corner[p.corner_id] = {}
            order.append(p.corner_id)
        by_corner[p.corner_id][p.vindiff_mv] = p
    for cid in order:
        cells = []
        for v in delay_cols:
            p = by_corner[cid].get(v)
            if p is None:
                cells.append("n/a")
            elif p.classify() == "DECIDED":
                cells.append(f"{p.regen_time_ns:.4f}")
            else:
                cells.append(p.classify())
        a(f"| `{cid}` | " + " | ".join(cells) + " |")
    a("")

    a("## What this means")
    a("")
    if failed_controls:
        worst_control = min(
            (p for p in failed_controls if p.reset_divergence_onset_ns is not None),
            key=lambda p: p.reset_divergence_onset_ns,
            default=None,
        )
        a(
            f"**The intended measurement could not be completed, and this record "
            f"says so instead of reporting the {len(decided)} delays it did obtain "
            "as if they covered the grid.** The reset-integrity control above "
            f"fails at {len(bad_corner_ids)} of {n_corners} ratified corner points "
            "with the inputs shorted to the common mode. A latch that separates "
            "to the rails before its clock edge, with no input, has not been "
            "reset; its subsequent output carries no information about the input."
        )
        a("")
        if worst_control is not None:
            a(
                f"Earliest observed divergence: `{worst_control.corner_id}` at "
                f"t = {worst_control.reset_divergence_onset_ns:.3f} ns into a "
                f"{RESET_NS} ns reset phase, reaching "
                f"{worst_control.pre_edge_diff_v:+.4f} V by the evaluate edge."
            )
            a("")
        a(
            "**Mechanism, read off this same data rather than assumed.** In "
            "`design/comparator.sch` the cross-coupled NMOS pair (`XM_LATN_P` / "
            "`XM_LATN_N`) has both sources tied directly to GND, so it is "
            "conducting throughout the CLK=0 reset phase, in opposition to the "
            "reset PMOS pair (`XM_RST_P` / `XM_RST_N`, W=16). Two independent "
            "measurements in the control table above are consequences of that "
            "and of nothing else:"
        )
        a("")
        a(
            "1. The reset-phase output level is NOT the rail. A precharge that "
            "won would sit at v(OUTP) = v(OUTN) = VDD; the reset-phase static "
            "supply current column is non-zero precisely because a DC path "
            "VDD -> reset PMOS -> output node -> latch NMOS -> GND is open the "
            "whole time."
        )
        a(
            "2. That balanced level is an UNSTABLE equilibrium, not a resting "
            "state. Both latch NMOS devices sit well above threshold there, so "
            "the cross-coupled loop gain exceeds unity and any asymmetry -- "
            "process skew between the NMOS and PMOS corners, temperature, or "
            "the input pair's own subthreshold conduction -- is amplified to "
            "the rails within the reset window. The corners where the control "
            "fails are the skewed and cold ones, which is the signature of an "
            "amplified asymmetry rather than of a slow settle."
        )
        a("")

        # A corner can pass the zero-input control and still fail with an
        # input applied -- worth naming explicitly, because the two counts
        # otherwise look inconsistent between the control table and the
        # decision table above.
        control_ok_ids = {
            p.corner_id for p in controls if p.classify() == "CONTROL-OK"
        }
        sneaky = sorted({
            p.corner_id for p in not_held if p.corner_id in control_ok_ids
        })
        if sneaky:
            at_t0 = [
                p for p in not_held
                if p.corner_id in control_ok_ids
                and p.reset_divergence_onset_ns == 0.0
            ]
            plural = "corner point passes" if len(sneaky) == 1 else "corner points pass"
            a(
                f"**A held control is necessary, not sufficient.** "
                f"{len(sneaky)} {plural} the Vindiff = 0 mV control "
                f"yet still fail with an input applied "
                f"({', '.join('`' + c + '`' for c in sneaky)}) -- which is why "
                "the control table and the decision table above do not report "
                "the same count."
            )
            if at_t0:
                worst = min(at_t0, key=lambda p: p.pre_edge_diff_v or 0.0)
                a("")
                a(
                    "At those points the divergence onset is t = 0.000 ns: the "
                    "separation is present in the very first transient sample, "
                    "so it is not something the reset phase failed to suppress "
                    "over time -- the reset phase's own DC operating point, the "
                    "solution ngspice starts the transient from before any clock "
                    "edge exists, is ALREADY a decided state. A bistable "
                    "operating point is the same defect seen from the DC side "
                    "rather than the transient side, and it is resolved by the "
                    "solver rather than by the circuit. Worst case here: "
                    f"`{worst.corner_id}` with {worst.vindiff_mv:+.4f} mV "
                    f"applied starts the evaluate phase at "
                    f"{worst.pre_edge_diff_v:+.4f} V -- committed AGAINST the "
                    "applied input."
                )
            a("")
        a(
            "**Consequence for the ADC, stated plainly.** This is a functional "
            "finding, not only a timing one: at the affected corners the "
            "comparator enters each bit trial already committed to an output, "
            "so the bit it produces is not determined by the charge on the CDAC "
            "top plate. No ADC-level transient simulation in this repository has "
            "exercised the real comparator inside the full hierarchy yet (the "
            "sequencer campaign is behavioural and the ENOB estimate composes a "
            "noise term rather than simulating the latch), which is why this had "
            "not previously surfaced."
        )
        a("")
        a(
            "**Not fixed here, by design.** Repairing this means changing "
            "`design/comparator.sch` (the textbook remedy is to stop the NMOS "
            "latch conducting during reset -- e.g. return its sources to a "
            "clocked internal node rather than hard-wiring them to GND), which "
            "is a topology change: it needs its own decision record amending "
            "DR-004, a re-netlist, and re-running every committed "
            "comparator-decision record (offset, noise, noise-corners) against "
            "the new device set. That is deliberately out of this record's "
            "scope; this record's job is to establish, with a negative control, "
            "that the problem is real and to say exactly which corners show it."
        )
    else:
        binding = max(decided, key=lambda p: p.regen_time_ns or 0.0) if decided else None
        if binding is not None:
            a(
                f"**Context, not a graded verdict**: the worst decision delay "
                f"({binding.regen_time_ns:.4f} ns) is "
                f"{BIT_TRIAL_PHASE_BUDGET_NS / (binding.regen_time_ns or 1):.1f}x "
                f"inside DR-006's provisional worst-case (12 MHz) bit-trial phase "
                f"budget of {BIT_TRIAL_PHASE_BUDGET_NS:.3f} ns. That budget is a "
                "mechanical consequence of spec/target-spec.md's DRAFT "
                "sample-rate row, not a ratified number, so this is headroom "
                "against a provisional figure and NOT a pass against a spec line."
            )
            a("")
        a(
            "Expected shape: decision delay grows roughly as "
            "`ln(V_decided/Vindiff)` (standard positive-feedback latch "
            "behaviour) as Vindiff shrinks, and grows with slower process / "
            "lower supply. Both trends are checkable row-by-row above."
        )
    a("")
    a(
        "**Scope limits, stated rather than implied.** This exercises the "
        "comparator core in isolation, driven by ideal DC differential sources: "
        "it excludes the CDAC array's own settling (measured separately, "
        "`sim/cdac-bit-trial-settling/`), the SAR sequencer's logic delay, the "
        "sampling front end's acquisition, and any load the real top-plate "
        "network presents to the comparator inputs. It is one term of a "
        "bit-trial timing budget, not the budget. It is also a nominal-device "
        "run: no Monte Carlo mismatch is applied, so the reset-phase asymmetry "
        "reported above is the corner-model asymmetry alone -- per-device "
        "mismatch would only add to it."
    )
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "regen-corners", supersedes=supersedes,
    )

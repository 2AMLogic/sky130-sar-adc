"""regen campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .common import (
    DECIDE_THRESHOLD_V,
    DUT_FRAGMENT,
    EXPERIMENT_DIR,
    RESET_NS,
    RESET_TR_NS,
    VCM,
    VDD,
    _dut_lines,
    _run,
)
from harness import evidence, pdk, toolchain

# ---------------------------------------------------------------------------
# regen: regeneration time vs. differential input (deterministic sweep)
# ---------------------------------------------------------------------------

DEFAULT_VINDIFF_SWEEP_MV = [0.5, 1, 2, 5, 10, 20, 50, -10]
EVALUATE_NS = 40.0
# in ns of absolute transient time, at which the common-mode and
# differential deviations are ALSO reported (issue #390). The end of the
# evaluate window is always appended to this list by run_kickback_sweep(),
# so the recovery table always closes on it. The evaluate edge starts at
# RESET_NS = 5 ns and the CLK ramp ends at 5.1 ns, so these three sit ~0.9,
# ~4.9 and ~14.9 ns past it: far enough out to say whether the disturbance
# is a transient that settles or a level that persists into the next bit
# trial, and spread widely enough to straddle the latch's own resolution
# instant, which moves by ~10 ns across this Vindiff grid. A pick-off is a
# RECOVERY INDICATOR, not a settling-time measurement -- the in-loop
# residual-at-next-decision quantity DR-011's Open items name needs a
# different (floating-top-plate) testbench and is deliberately out of
# scope here.


def _regen_deck(
    info: pdk.PdkInfo,
    corner: str,
    temp_c: float,
    vindiff_mv: float,
    log_name: str,
    supply_v: float = VDD,
    evaluate_ns: float = EVALUATE_NS,
    probe_supply_current: bool = False,
    title: str = "regen-time sweep",
    issue_ref: str = "(issue #54)",
    dut_fragment: Path = DUT_FRAGMENT,
    rndseed: int | None = None,
) -> str:
    """Single reset->evaluate transient deck for one (corner, temp, supply,
    Vindiff) point.

    `supply_v` and `evaluate_ns` default to the module constants, so the
    original `regen` subcommand's deck text is byte-identical to what it was
    before those two parameters existed. The `regen-corners` campaign below
    varies both.

    The input common mode tracks the supply (`Vcm = supply/2`) rather than
    staying pinned at the nominal 0.9 V: in THIS design `V_REF = V_DD`
    (DR-003 Item 1) and the CDAC's bottom-plate-switched common mode is
    `V_REF/2`, so a +-10% supply excursion moves the comparator's own input
    common mode with it. Holding Vcm fixed while the rail moved would
    simulate an operating point this design never presents to the
    comparator.

    `probe_supply_current` appends `i(Vdd)` to the `wrdata` vector list so
    the caller can read the supply current drawn during the CLK=0 reset
    phase. It is off by default so that the `regen` subcommand's deck text
    stays byte-identical to what produced its already-committed records.

    `title`/`issue_ref` name the campaign in the deck's own leading comment
    line, which is what a reader of a raw log under `corners/<record-id>/`
    sees first. Both default to the original strings, so an unspecified call
    still produces byte-identical deck text; `offset-bisect` below passes its
    own so its probe logs are not mislabelled as regen-time runs. The STIMULUS is
    deliberately identical either way -- that is what makes an `offset-bisect`
    boundary directly comparable with a `regen`/`regen-corners` delay taken at
    the same Vindiff.

    `rndseed` (issue #524) emits `.option rndseed=N` right after `.temp`, the
    same placement `_pickoff_deck()` uses, so a per-draw Monte Carlo probe on
    a `*_mm` corner is reproducible. None (the default) emits nothing, keeping
    every pre-existing caller's deck text byte-identical."""
    vindiff_v = vindiff_mv / 1000.0
    vcm = supply_v / 2.0
    period_ns = RESET_NS + RESET_TR_NS + evaluate_ns + 10.0
    tstop_ns = RESET_NS + RESET_TR_NS + evaluate_ns
    lines = [
        f"* comparator-decision {title} -- vindiff={vindiff_mv}mV "
        f"corner={corner} temp={temp_c}C {issue_ref}",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        *([f".option rndseed={rndseed}"] if rndseed is not None else []),
        "",
        "Vdd VDD 0 dc {vdd_val}",
        f"Vclk CLK 0 PULSE(0 {{vdd_val}} {RESET_NS}n {RESET_TR_NS}n {RESET_TR_NS}n "
        f"{evaluate_ns}n {period_ns}n)",
        f"Vinp VINP 0 dc {vcm + vindiff_v / 2}",
        f"Vinn VINN 0 dc {vcm - vindiff_v / 2}",
        "",
        _dut_lines(dut_fragment),
        "",
        ".control",
        f"tran 0.005n {tstop_ns}n",
        f"wrdata {log_name}.csv v(CLK) v(OUTP) v(OUTN)"
        + (" i(Vdd)" if probe_supply_current else ""),
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


# Fraction of the supply that |v(OUTP) - v(OUTN)| must stay BELOW at the last
# sample before the evaluate edge for the reset phase to count as having held
# the latch balanced. 5% of the rail (90 mV at 1.8 V) is ~25x the largest
# differential input this campaign applies (10 mV) and ~51x the half-LSB input
# (1.7578 mV), so a point inside it cannot have been pre-decided in any sense
# that would bias the measured decision delay; a point outside it has already
# separated by more than any input could account for.
RESET_HOLD_TOLERANCE_FRAC = 0.05


@dataclass
class RegenPoint:
    vindiff_mv: float
    regen_time_ns: float | None
    log_text: str
    # Reset-phase integrity instrumentation. `pre_edge_diff_v` is
    # v(OUTP) - v(OUTN) at the last sample strictly BEFORE the CLK edge
    # begins rising; on a latch whose reset actually holds it is ~0 V.
    # `reset_divergence_onset_ns` is the first time during the reset phase at
    # which |v(OUTP) - v(OUTN)| exceeded the same tolerance (None if it never
    # did). `reset_static_idd_a` is the supply current at that same pre-edge
    # sample (None unless the deck was built with probe_supply_current).
    pre_edge_diff_v: float | None = None
    final_diff_v: float | None = None
    reset_divergence_onset_ns: float | None = None
    reset_static_idd_a: float | None = None


def run_regen_sweep(
    corner: str = "tt", temp_c: float = 27.0,
    vindiff_sweep_mv: list[float] | None = None, quiet: bool = False,
    supply_v: float = VDD, evaluate_ns: float = EVALUATE_NS,
    probe_supply_current: bool = False,
) -> list[RegenPoint]:
    info = pdk.resolve_or_raise()
    vindiff_sweep_mv = vindiff_sweep_mv or DEFAULT_VINDIFF_SWEEP_MV
    evaluate_start_ns = RESET_NS + RESET_TR_NS
    # The "decided" threshold tracks the rail (0.5*supply), the same fraction
    # DECIDE_THRESHOLD_V encodes at the nominal supply -- a fixed 0.9 V
    # threshold would be a different fraction of a decided output at 1.62 V
    # or 1.98 V, so the per-corner numbers would not be comparable.
    decide_threshold_v = 0.5 * supply_v
    reset_hold_tol_v = RESET_HOLD_TOLERANCE_FRAC * supply_v
    points: list[RegenPoint] = []
    with tempfile.TemporaryDirectory(prefix="comparator-decision-regen-") as scratch:
        scratch_dir = Path(scratch)
        for vindiff_mv in vindiff_sweep_mv:
            log_name = f"regen_{vindiff_mv}mV".replace("-", "neg").replace(".", "p")
            deck = _regen_deck(
                info, corner, temp_c, vindiff_mv, log_name,
                supply_v=supply_v, evaluate_ns=evaluate_ns,
                probe_supply_current=probe_supply_current,
            )
            log_text = _run(deck, scratch_dir, log_name)
            csv_path = scratch_dir / f"{log_name}.csv"
            if probe_supply_current:
                t, clk, outp, outn, idd = toolchain.read_wrdata_csv(csv_path, 4)
            else:
                t, clk, outp, outn = toolchain.read_wrdata_csv(csv_path, 3)
                idd = None
            sign = 1.0 if vindiff_mv >= 0 else -1.0
            regen_ns = None
            for i, tt in enumerate(t):
                if tt < evaluate_start_ns * 1e-9:
                    continue
                diff = sign * (outp[i] - outn[i])
                if diff > decide_threshold_v:
                    regen_ns = (tt - evaluate_start_ns * 1e-9) * 1e9
                    break

            # Reset-phase integrity: everything strictly before the CLK edge
            # STARTS rising (RESET_NS, not evaluate_start_ns -- the 100 ps edge
            # itself already belongs to the evaluate transition).
            pre_edge_diff_v = None
            reset_static_idd_a = None
            onset_ns = None
            reset_idx = [i for i, tt in enumerate(t) if tt < RESET_NS * 1e-9]
            if reset_idx:
                last = reset_idx[-1]
                pre_edge_diff_v = outp[last] - outn[last]
                if idd is not None:
                    reset_static_idd_a = idd[last]
                for i in reset_idx:
                    if abs(outp[i] - outn[i]) > reset_hold_tol_v:
                        onset_ns = t[i] * 1e9
                        break

            points.append(RegenPoint(
                vindiff_mv=vindiff_mv, regen_time_ns=regen_ns, log_text=log_text,
                pre_edge_diff_v=pre_edge_diff_v,
                final_diff_v=(outp[-1] - outn[-1]) if t else None,
                reset_divergence_onset_ns=onset_ns,
                reset_static_idd_a=reset_static_idd_a,
            ))
            if not quiet:
                shown = f"{regen_ns:.4f}ns" if regen_ns is not None else "UNRESOLVED"
                extra = ""
                if pre_edge_diff_v is not None and abs(pre_edge_diff_v) > reset_hold_tol_v:
                    extra = (
                        f"  [RESET NOT HELD: pre-edge diff={pre_edge_diff_v:+.4f}V"
                        + (f", onset={onset_ns:.3f}ns" if onset_ns is not None else "")
                        + "]"
                    )
                print(f"  vindiff={vindiff_mv:+.4f}mV -> regen_time={shown}{extra}")
    return points


def _finalize_record(
    lines: list[str],
    record_path: Path,
    pdk_line: str,
    ng_version: str,
    netlist_sha: str,
    cmd: str,
    extra: dict[str, str] | None = None,
    supersedes: str = "",
) -> Path:
    """Shared tail for the write_*_evidence() functions below: append the
    environment block + footer boilerplate and write the record. `cmd` is
    the subcommand name (e.g. "regen", "offset", "noise"), used to build
    the "Written by" attribution.

    `supersedes` is the prior `<record-id>` this record REPLACES for the same
    claim, per sim/README.md's "Correction-supersession vs distinct-claim"
    rule -- empty (rendered "(none)") for a record that tests a different
    claim, however closely related. It is machine-load-bearing, not
    decoration: `sim/report/generate.py --check`'s freshness gate
    (`find_superseding_sibling()`) fails the build when a record cited by
    `sim/report/manifest.py` has been superseded by a sibling in the same
    `records/` directory, and it discovers that ONLY through the sibling's own
    **Supersedes** field. A re-characterization that mints new records without
    filling this in leaves the superseded ones citable forever with nothing to
    detect it. It is a CLI argument rather than a constant because which
    record is superseded is a per-run fact.
    """
    lines.extend(evidence.environment_block(
        pdk_line=pdk_line,
        ngspice_line=ng_version,
        netlist_sha256=netlist_sha,
        extra=extra,
    ))
    lines.append("")
    lines.extend(evidence.footer_lines(f"sim/comparator-decision/run.py {cmd}", supersedes))
    record_path.write_text("\n".join(lines))
    return record_path


def write_regen_evidence(
    points: list[RegenPoint], corner: str, temp_c: float,
    note: str = "", supersedes: str = "",
) -> Path:
    raw_logs: dict[str, str] = {}
    for p in points:
        safe = f"{p.vindiff_mv}mV".replace("-", "neg").replace(".", "p")
        raw_logs[f"vindiff_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(EXPERIMENT_DIR, _dut_lines(), "corners", raw_logs)
    record_path = prov.record_path
    a = lines.append
    a(
        "- **Claim**: pending #1/#27 -- characterizes design/comparator.sch's "
        "regeneration time vs. differential input at one PVT point. Not a "
        "spec/target-spec.md row (no sample-rate/settling row is ratified "
        "yet); informational for the future comparator-topology decision "
        "record and #28's corner campaign."
    )
    a(f"- **Netlist provenance**: schematic (`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}`)")
    a(
        f"- **Corner matrix run**: process=['{corner}'], temperature_c=[{temp_c}], "
        f"supply_v=[{VDD}] (1 PVT point -- **subset-corner justification**: this "
        "is a first-pass characterization at the nominal corner only; a full "
        "PVT sweep of this same Vindiff grid is deferred to #28's corner "
        "campaign once a comparator-topology decision record exists, per "
        "sim/README.md's 'Subset-corner justification')"
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK={VDD}V) "
        f"edge per run (not a repeating clock -- each ngspice invocation starts "
        f"from an uninitialized circuit, so there is no multi-cycle state to "
        f"carry); decision threshold |v(outp)-v(outn)| > {DECIDE_THRESHOLD_V}V "
        f"(0.5*VDD); Vcm={VCM}V"
    )
    if note:
        a(f"- **Note**: {note}")
    unresolved = [p for p in points if p.regen_time_ns is None]
    a(f"- **Overall**: {'PASS' if not unresolved else 'INCOMPLETE'} "
      f"({len(points) - len(unresolved)}/{len(points)} points resolved within the "
      f"{EVALUATE_NS}ns evaluate window)")
    a("")
    a("## Regeneration time vs. differential input")
    a("")
    a("| Vindiff (mV) | regen time (ns) |")
    a("|---|---|")
    for p in sorted(points, key=lambda p: p.vindiff_mv):
        shown = f"{p.regen_time_ns:.4f}" if p.regen_time_ns is not None else "UNRESOLVED (> evaluate window)"
        a(f"| {p.vindiff_mv:+.2f} | {shown} |")
    a("")
    a(
        "Expected shape: regeneration time grows roughly as `ln(V_decided/Vindiff)` "
        "(standard positive-feedback latch behavior) as Vindiff shrinks -- the "
        "monotonic growth from 50mV to 0.5mV above is the qualitative check for "
        "that, not a quantitative claim against any ratified settling-time row."
    )
    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "regen", supersedes=supersedes,
    )

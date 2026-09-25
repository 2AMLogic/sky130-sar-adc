#!/usr/bin/env python3
"""Ground-return / supply-terminal impedance campaign on the assembled
`design/sar_adc_top.spice` (issue #378, DR-012's "the impedance argument is
unmeasured" open item).

    source sim/env.sh
    python3 sim/ground-return-impedance/run_ground_return.py --check-env
    python3 sim/ground-return-impedance/run_ground_return.py            # baseline corner, every arm
    SIM_NGSPICE_TIMEOUT_S=3600 python3 sim/ground-return-impedance/run_ground_return.py \\
        --corners --record --jobs 12

WHY THIS EXISTS. DR-012 (issue #362) decided the block presents a DRAWN analog
`GND` pad instead of reaching board ground through the substrate only. Its
reasoning was, in its own words, a design-time argument: every campaign in
`sim/` drives all four supply terminals (`VDD`, `GND`, `VPWR`, `VGND`) from
ideal zero-impedance sources, so no testbench had ever put an impedance in
the ground return at all. This campaign is the testbench DR-012 names: the
same whole-ADC stimulus `sim/full-conversion-transient/` runs, with the four
supply terminals driven through package-like series R+L, and a lumped
substrate resistance standing in for the on-die p-substrate path.

WHAT IS REUSED, NOT COPIED. The DUT (`design/sar_adc_top.spice`), the
stimulus/measurement fragment
(`sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`),
the deck assembly (`run_conversion.assemble_deck()`), the decoder
(`run_conversion.decode()`) and the ratified OAT grid are all imported from
`sim/full-conversion-transient/` read-only. That file is not edited here
(issues #267/#269 are active on it). Everything this campaign adds is a
TESTBENCH-ONLY rewrite of the assembled deck text, below.

TWO TESTBENCH-ONLY DECK REWRITES (never written back to design/):

  1. `GND` -> `GND_DIE` in the DUT body. ngspice treats a node literally
     named `gnd` as an alias of node `0` (the simulator's reference), so in
     every existing campaign the analog ground is not merely *ideal*, it is
     the reference node itself -- no element can be placed in series with it.
     Renaming the net (on non-comment lines, whole-token, case-sensitive so
     `VGND` is untouched) turns it into an ordinary node a package network
     can be attached to. The `ideal` arm then ties `GND_DIE` to `0` through a
     0 V source, which is electrically identical to the unrenamed deck; the
     `--rename-control` run proves that on the simulator rather than by
     assertion (identical codes, required, or the run fails).
  2. The fragment's three supply sources (`VVDD`, `VVPWR`, `VVGND`) are
     re-pointed at board-side nodes and joined to the die-side nodes the DUT
     uses through the arm's network, and a fourth source `VVGNDA` is added for
     the analog ground pad. The source names -- and therefore the fragment's
     own `avg i(vvdd)` / `avg i(vvpwr)` measurements -- are unchanged.

Board side is ideal throughout (sources to node `0`, no board impedance, no
board decoupling), and `VREFP`/`VREFN`/`VCM`/inputs/`CLK`/`RST_B` stay ideal
sources referenced to board ground `0` -- see README.md "What this can and
cannot claim" for what that leaves out.

THE ARMS (see `ARMS` below; README.md has the table and the derivation of
every value):

  ideal            -- every terminal ideal: the baseline every other campaign uses.
  pkg              -- R+L on all four terminals; GND and VGND joined by nothing
                      on die (the schematic's own two-net view).
  pkg-sub<R>       -- as `pkg`, plus the lumped substrate resistance joining
                      GND_DIE and VGND on die (DR-012: they are ONE extracted
                      node through the p-substrate). The pad as DR-012 decided it.
  sub-nopad-<R>    -- no GND pad at all; GND_DIE reaches the outside only
                      through the lumped substrate resistance to VGND, whose
                      own pad (and VDD/VPWR's) is IDEAL. Substrate resistance
                      alone, no inductance: separates "on-die substrate
                      return" from "bond inductance".
  pkg-nopad-<R>    -- DR-012's rejected null option under a package: no GND
                      pad, GND_DIE reaches VGND only through the substrate
                      resistance, and VDD/VPWR/VGND bond through R+L.

The substrate resistance is a LUMPED STAND-IN at two values a decade and more
apart (`R_SUB_OHM`), not an extraction: no substrate network exists in this
repo. The record says so in its own words.

WHAT IS MEASURED. Per arm and PVT point: the captured code for each of the
five inputs (the fragment's own), its change against the `ideal` arm at the
SAME corner (the quantity this campaign is about: code movement attributable
to the supply network), the 12-period phase structure, and die-side
bounce -- min/max of each die supply node against board ground, and the
worst-case die-side analog supply `v(VDD) - v(GND_DIE)` -- over the five
measured conversions.

Nothing here is graded against a spec row: no row of `spec/target-spec.md`
names a supply-impedance tolerance, and this campaign proposes none.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import os
import re
import sys
import tempfile
import time
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
SIM_DIR = EXPERIMENT_DIR.parent
FCT_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(FCT_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

import gen_full_conversion_tb as tb  # noqa: E402  (the reused stimulus's own constants)
import run_conversion as fct  # noqa: E402  (the reused deck assembly + decoder)

REPO_ROOT = evidence.REPO_ROOT
RUNNER_REL = "sim/ground-return-impedance/run_ground_return.py"

# --------------------------------------------------------------------------
# Package / substrate model -- every value derived in README.md
# ("Where the R+L values come from"); restated here so the record can quote
# the exact numbers the deck used.
# --------------------------------------------------------------------------
# One bond wire per supply terminal: 25 um diameter gold, 2 mm long.
BOND_WIRE_DIAMETER_UM = 25.0
BOND_WIRE_LENGTH_MM = 2.0
GOLD_RESISTIVITY_OHM_M = 2.44e-8  # bulk Au at room temperature
MU0 = 4e-7 * 3.141592653589793


def bond_wire_inductance_h(length_mm: float, diameter_um: float) -> float:
    """Low-frequency self-inductance of a straight round wire far from any
    return conductor: L = (mu0 * l / 2pi) * (ln(2l/r) - 3/4). An isolated
    straight wire is the standard first-order bond-wire model; a real loop's
    mutual coupling to its neighbours is not modelled (README.md)."""
    import math

    length_m = length_mm * 1e-3
    radius_m = diameter_um * 1e-6 / 2.0
    return MU0 * length_m / (2 * math.pi) * (math.log(2 * length_m / radius_m) - 0.75)


def bond_wire_resistance_ohm(length_mm: float, diameter_um: float) -> float:
    """DC resistance R = rho * l / A. Skin effect raises it at GHz; using the
    DC value UNDER-damps the package LC, which is the pessimistic direction
    for supply ringing (README.md)."""
    import math

    radius_m = diameter_um * 1e-6 / 2.0
    return GOLD_RESISTIVITY_OHM_M * length_mm * 1e-3 / (math.pi * radius_m**2)


L_PKG_H = round(bond_wire_inductance_h(BOND_WIRE_LENGTH_MM, BOND_WIRE_DIAMETER_UM), 11)  # 2.0 nH
R_PKG_OHM = round(bond_wire_resistance_ohm(BOND_WIRE_LENGTH_MM, BOND_WIRE_DIAMETER_UM), 3)  # 0.099

# Lumped substrate resistance between the analog ground's taps (GND_DIE) and
# the digital ground's taps (VGND). A stand-in, bracketed rather than chosen:
# 10 ohm is the low end of DR-012's own "10s of ohms" figure, 1 kohm is two
# decades above it. Neither is an extraction.
R_SUB_OHM: tuple[float, ...] = (10.0, 1000.0)

# The four supply terminals as (terminal label, fragment source instance,
# die-side node the DUT uses after the GND rename, board-side potential).
TERMINALS: tuple[tuple[str, str, str, str], ...] = (
    ("VDD", "VVDD", "VDD", "{vdd_val}"),
    ("VPWR", "VVPWR", "VPWR", "{vdd_val}"),
    ("VGND", "VVGND", "VGND", "0"),
    ("GND", "VVGNDA", "GND_DIE", "0"),
)

# The committed fragment's own supply lines this campaign rewrites. Matching
# them exactly (count == 1 each) is what makes a reshaped fragment fail loudly
# rather than silently leave an ideal source in place.
FRAGMENT_SUPPLY_LINES = {
    "VVDD": "VVDD VDD 0 DC {vdd_val}",
    "VVPWR": "VVPWR VPWR 0 DC {vdd_val}",
    "VVGND": "VVGND VGND 0 DC 0",
}


@dataclasses.dataclass(frozen=True)
class Arm:
    name: str
    package: bool  # R+L on every bonded terminal (else ideal bonds)
    gnd_pad: bool  # is GND_DIE bonded at all (DR-012's decision)
    r_sub_ohm: float | None  # lumped GND_DIE <-> VGND substrate resistance
    what: str


def _fmt_ohm(r: float) -> str:
    return f"{r / 1000:g}k" if r >= 1000 else f"{r:g}"


ARMS: tuple[Arm, ...] = (
    Arm("ideal", False, True, None,
        "every terminal ideal -- the baseline every existing campaign uses"),
    Arm("pkg", True, True, None,
        "R+L on all four terminals; GND and VGND not joined on die"),
    *(
        Arm(f"pkg-sub{_fmt_ohm(r)}", True, True, r,
            f"R+L on all four terminals + {r:g} ohm substrate tie GND_DIE<->VGND "
            "(the pad as DR-012 decided it)")
        for r in R_SUB_OHM
    ),
    *(
        Arm(f"sub-nopad-{_fmt_ohm(r)}", False, False, r,
            f"no GND pad; GND_DIE reaches VGND only through {r:g} ohm substrate; "
            "every bonded terminal ideal (substrate resistance alone)")
        for r in R_SUB_OHM
    ),
    *(
        Arm(f"pkg-nopad-{_fmt_ohm(r)}", True, False, r,
            f"no GND pad; GND_DIE reaches VGND only through {r:g} ohm substrate; "
            "VDD/VPWR/VGND through R+L (DR-012's rejected null option)")
        for r in R_SUB_OHM
    ),
)
ARMS_BY_NAME = {a.name: a for a in ARMS}
BASELINE_ARM = "ideal"

# --------------------------------------------------------------------------
# Deck rewrites (pure text -- pinned by sim/tests/test_ground_return.py)
# --------------------------------------------------------------------------
_GND_TOKEN = re.compile(r"(?<![A-Za-z0-9_])GND(?![A-Za-z0-9_])")


def rename_analog_ground(dut_text: str) -> str:
    """Rewrite 1: `GND` -> `GND_DIE` on every non-comment line, whole-token
    and case-sensitive (`VGND`, `GND|...` substrings of other names are never
    touched). Fails if the result still contains any `gnd` token ngspice
    would alias to node 0, or if the DUT changed shape so the rename hit
    nothing."""
    out: list[str] = []
    hits = 0
    for ln in dut_text.splitlines():
        if ln.lstrip().startswith("*"):
            out.append(ln)
            continue
        new, n = _GND_TOKEN.subn("GND_DIE", ln)
        hits += n
        out.append(new)
    if hits == 0:
        raise RuntimeError(
            "rename_analog_ground: no whole-token GND found in the DUT -- the netlist "
            "changed shape; re-derive this campaign's deck rewrite."
        )
    text = "\n".join(out) + ("\n" if dut_text.endswith("\n") else "")
    leftover = [
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("*")
        and re.search(r"(?<![A-Za-z0-9_])gnd(?![A-Za-z0-9_])", ln, re.I)
    ]
    if leftover:
        raise RuntimeError(
            "rename_analog_ground: a ground-aliased 'gnd' token survived the rename: "
            + leftover[0]
        )
    return text


def supply_network_lines(arm: Arm) -> list[str]:
    """The SPICE lines that replace the fragment's three supply sources for
    `arm` (plus the analog-ground pad source and the substrate tie)."""
    lines = [
        f"* --- issue #378 supply-return network, arm '{arm.name}': {arm.what}",
        f"* package per bonded terminal: R = {R_PKG_OHM:g} ohm, L = {L_PKG_H * 1e9:g} nH "
        f"({BOND_WIRE_LENGTH_MM:g} mm x {BOND_WIRE_DIAMETER_UM:g} um Au bond wire)"
        if arm.package else "* bonded terminals ideal (no package R+L)",
    ]
    for label, src, die_node, potential in TERMINALS:
        if label == "GND" and not arm.gnd_pad:
            lines.append("* GND: no pad -- GND_DIE is not bonded (DR-012's null option)")
            continue
        if arm.package:
            b, m = f"{label}_BRD", f"{label}_PKGM"
            lines += [
                f"{src} {b} 0 DC {potential}",
                f"RPKG_{label} {b} {m} {R_PKG_OHM:g}",
                f"LPKG_{label} {m} {die_node} {L_PKG_H:.4e}",
            ]
        else:
            lines.append(f"{src} {die_node} 0 DC {potential}")
    if arm.r_sub_ohm is not None:
        lines += [
            f"* lumped substrate stand-in (NOT an extraction): {arm.r_sub_ohm:g} ohm",
            f"RSUB GND_DIE SUB_SENSE {arm.r_sub_ohm:g}",
            "VISUB SUB_SENSE VGND DC 0",
        ]
    return lines


def rewrite_supplies(deck: str, arm: Arm) -> str:
    """Rewrite 2: replace the fragment's three supply-source lines with the
    arm's network. Each original line must appear exactly once."""
    lines = deck.splitlines()
    idx: dict[str, int] = {}
    for key, want in FRAGMENT_SUPPLY_LINES.items():
        found = [i for i, ln in enumerate(lines) if ln.strip() == want]
        if len(found) != 1:
            raise RuntimeError(
                f"rewrite_supplies: expected exactly one {want!r} line in the assembled "
                f"deck, found {len(found)} -- the full-conversion fragment changed shape."
            )
        idx[key] = found[0]
    first = min(idx.values())
    drop = set(idx.values())
    out = []
    for i, ln in enumerate(lines):
        if i == first:
            out.extend(supply_network_lines(arm))
        if i in drop:
            continue
        out.append(ln)
    return "\n".join(out) + "\n"


def bounce_window_ns() -> tuple[float, float]:
    """From the first measured conversion's first edge to the end of the
    transient: the five conversions whose codes are graded."""
    first = tb.measured_conversions()[0]
    return tb.t_edge_ns(tb.PHASES_PER_CONVERSION * first), tb.t_stop_ns()


def idd_window_ns() -> tuple[float, float]:
    c = tb.IDD_CONVERSION
    return (
        tb.t_edge_ns(tb.PHASES_PER_CONVERSION * c),
        tb.t_edge_ns(tb.PHASES_PER_CONVERSION * (c + 1)),
    )


BOUNCE_NODES: tuple[tuple[str, str], ...] = (
    ("gnd_die", "v(gnd_die)"),
    ("vgnd", "v(vgnd)"),
    ("vdd", "v(vdd)"),
    ("vpwr", "v(vpwr)"),
)


def extra_measure_lines(arm: Arm) -> list[str]:
    t0, t1 = bounce_window_ns()
    i0, i1 = idd_window_ns()
    lines = [
        "* --- issue #378 die-side bounce probes (read-only) ---",
    ]
    for name, expr in BOUNCE_NODES:
        lines.append(f".meas tran {name}_max max {expr} from={t0:.4f}n to={t1:.4f}n")
        lines.append(f".meas tran {name}_min min {expr} from={t0:.4f}n to={t1:.4f}n")
    # ngspice's .meas does not accept the two-node v(a,b) form (it reports
    # "no such vector"); the difference has to go through par().
    lines.append(
        f".meas tran vdda_min min par('v(vdd)-v(gnd_die)') from={t0:.4f}n to={t1:.4f}n"
    )
    lines.append(
        f".meas tran vdda_max max par('v(vdd)-v(gnd_die)') from={t0:.4f}n to={t1:.4f}n"
    )
    if arm.gnd_pad:
        lines.append(f".meas tran i_vgnda avg i(vvgnda) from={i0:.4f}n to={i1:.4f}n")
    lines.append(f".meas tran i_vgnd avg i(vvgnd) from={i0:.4f}n to={i1:.4f}n")
    if arm.r_sub_ohm is not None:
        lines.append(f".meas tran i_sub avg i(visub) from={i0:.4f}n to={i1:.4f}n")
    return lines


def extra_measure_names(arm: Arm) -> list[str]:
    names = []
    for name, _expr in BOUNCE_NODES:
        names += [f"{name}_max", f"{name}_min"]
    names += ["vdda_min", "vdda_max", "i_vgnd"]
    if arm.gnd_pad:
        names.append("i_vgnda")
    if arm.r_sub_ohm is not None:
        names.append("i_sub")
    return names


def assemble_arm_deck(
    dut_text: str, pdk_info: pdk.PdkInfo, arm: Arm, pc: str, tc: float, sv: float
) -> str:
    deck = fct.assemble_deck(
        rename_analog_ground(dut_text), pdk_info, pc, tc, sv,
        extra_meas=extra_measure_lines(arm),
    )
    deck = deck.replace(
        "* sim/full-conversion-transient -- end-to-end full-conversion transient",
        f"* sim/ground-return-impedance (issue #378) arm '{arm.name}' -- reusing\n"
        "* sim/full-conversion-transient -- end-to-end full-conversion transient",
        1,
    )
    return rewrite_supplies(deck, arm)


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------
def toolchain_key() -> str:
    """The part of the toolchain a cached log depends on: the ngspice version
    and the resolved PDK revision (not the Python version, which never
    touches a simulation)."""
    return "\n".join(
        ln for ln in toolchain.summary().splitlines()
        if ln.startswith("ngspice:") or ln.startswith("PDK:")
    )


def cache_path(cache_dir: Path, log_name: str, deck: str, tool_key: str) -> Path:
    """A cached raw log is keyed on the EXACT deck text and the toolchain key,
    so a log is only ever reused for a byte-identical deck on the same
    simulator and PDK revision -- i.e. a re-run that would produce it anyway."""
    digest = hashlib.sha256((tool_key + "\n" + deck).encode("utf-8")).hexdigest()[:16]
    return cache_dir / f"{log_name}__{digest}.log"


def run_deck(
    deck: str, scratch: Path, log_name: str, cache_dir: Path | None, tool_key: str
) -> tuple[str, bool]:
    """Run one deck (or reuse its cached raw log). Returns (log_text, cached).

    One point of this campaign is a whole-ADC transient that can take well
    over an hour on a contended host, and a point that exhausts its retries
    raises and ends the invocation. `--cache-dir` makes such an invocation
    resumable: every finished point's raw log is kept, and a later
    invocation reuses it instead of re-simulating the identical deck. The
    record states how many points were reused."""
    path = cache_path(cache_dir, log_name, deck, tool_key) if cache_dir else None
    if path is not None and path.is_file():
        return path.read_text(), True
    log_text = toolchain.run_ngspice_with_retry(deck, scratch, log_name, attempts=3)
    if path is not None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(log_text)
        tmp.replace(path)
    return log_text, False


def run_point(
    dut_text: str, pdk_info: pdk.PdkInfo, scratch: Path, arm: Arm,
    pc: str, tc: float, sv: float, cache_dir: Path | None = None, tool_key: str = "",
) -> dict:
    cid = corners_mod.corner_id(pc, tc, sv)
    deck = assemble_arm_deck(dut_text, pdk_info, arm, pc, tc, sv)
    t0 = time.time()
    log_text, cached = run_deck(deck, scratch, f"gri_{arm.name}_{cid}", cache_dir, tool_key)
    wall_s = time.time() - t0
    names = tb.all_measure_names() + extra_measure_names(arm)
    parsed = measure.parse(log_text, names, anchored=False)
    missing = measure.missing(parsed, names)
    result = fct.decode(parsed, sv)
    result.update(
        arm=arm.name, process_corner=pc, temp_c=tc, supply_v=sv, corner_id=cid,
        extra={n: parsed.get(n) for n in extra_measure_names(arm)},
        missing=missing, log_text=log_text, deck=deck, wall_s=wall_s, cached=cached,
    )
    if missing:
        result["all_ok"] = False
    return result


def run_rename_control(
    dut_text: str, pdk_info: pdk.PdkInfo, scratch: Path,
    cache_dir: Path | None = None, tool_key: str = "",
) -> dict:
    """The as-committed, UNRENAMED deck exactly as sim/full-conversion-
    transient assembles it (GND is the ngspice reference node), at the
    baseline corner. Its codes must equal the `ideal` arm's at the same
    corner, or the rename changed the circuit."""
    pc, tc, sv = fct.BASELINE_CORNER
    deck = fct.assemble_deck(dut_text, pdk_info, pc, tc, sv)
    log_text, cached = run_deck(deck, scratch, "gri_rename_control", cache_dir, tool_key)
    names = tb.all_measure_names()
    parsed = measure.parse(log_text, names, anchored=False)
    result = fct.decode(parsed, sv)
    result.update(
        arm="rename-control", corner_id=corners_mod.corner_id(pc, tc, sv),
        missing=measure.missing(parsed, names), log_text=log_text, cached=cached,
    )
    return result


def codes(point: dict) -> list[int | None]:
    return [cv["code"] for cv in point["conversions"]]


def format_point(point: dict) -> str:
    cs = " ".join("?" if c is None else str(c) for c in codes(point))
    ex = point.get("extra", {})
    gb = ex.get("gnd_die_max"), ex.get("gnd_die_min")
    gnd = "n/a" if None in gb else f"{1e3 * (gb[0] - gb[1]):.1f}mV"
    return (
        f"{point['arm']:>16} {point['corner_id']}: codes {cs} "
        f"phases_ok={point['n_phase_ok']}/{point['n_conversions']} "
        f"GND_DIE p-p={gnd} ("
        + ("cached" if point.get("cached") else f"{point['wall_s']:.0f}s") + ")"
        + (f" MISSING {len(point['missing'])}" if point["missing"] else "")
    )


def run_campaign(
    arms: list[Arm], corners_mode: bool, jobs: int, quiet: bool, scratch: Path,
    rename_control: bool, cache_dir: Path | None = None,
) -> tuple[list[dict], dict | None, str]:
    pdk_info = pdk.resolve()
    tool_key = toolchain_key() if cache_dir is not None else ""
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    dut_text = fct.dut_text()
    grid = (
        corners_mod.ratified_oat_grid(
            fct.NOMINAL_SUPPLY_V, fct.SUPPLY_TOLERANCE, fct.PROCESS_CORNERS, fct.TEMPS_C
        )
        if corners_mode
        else [fct.BASELINE_CORNER]
    )
    jobs_list = [(arm, pc, tc, sv) for arm in arms for pc, tc, sv in grid]
    done: dict[tuple, dict] = {}
    control: dict | None = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futs = {
            pool.submit(
                run_point, dut_text, pdk_info, scratch, arm, pc, tc, sv, cache_dir, tool_key
            ): (arm.name, pc, tc, sv)
            for arm, pc, tc, sv in jobs_list
        }
        ctrl_fut = (
            pool.submit(run_rename_control, dut_text, pdk_info, scratch, cache_dir, tool_key)
            if rename_control
            else None
        )
        for fut in concurrent.futures.as_completed(futs):
            point = fut.result()
            done[futs[fut]] = point
            if not quiet:
                print("  " + format_point(point), flush=True)
        if ctrl_fut is not None:
            control = ctrl_fut.result()
    points = [done[(arm.name, pc, tc, sv)] for arm, pc, tc, sv in jobs_list]
    return points, control, dut_text


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def baseline_for(points: list[dict], point: dict) -> dict | None:
    return next(
        (p for p in points if p["arm"] == BASELINE_ARM and p["corner_id"] == point["corner_id"]),
        None,
    )


def code_deltas(point: dict, base: dict | None) -> list[int | None]:
    if base is None:
        return [None] * len(point["conversions"])
    out = []
    for a, b in zip(codes(point), codes(base)):
        out.append(None if a is None or b is None else a - b)
    return out


def arm_summary(points: list[dict], arm_name: str) -> dict:
    mine = [p for p in points if p["arm"] == arm_name]
    moved = 0
    max_abs = 0
    unknown = 0
    total = 0
    worst_gnd_pp = 0.0
    worst_vdda_min = None
    phase_ok = True
    for p in mine:
        for d in code_deltas(p, baseline_for(points, p)):
            total += 1
            if d is None:
                unknown += 1
            elif d != 0:
                moved += 1
                max_abs = max(max_abs, abs(d))
        ex = p.get("extra", {})
        if ex.get("gnd_die_max") is not None and ex.get("gnd_die_min") is not None:
            worst_gnd_pp = max(worst_gnd_pp, ex["gnd_die_max"] - ex["gnd_die_min"])
        v = ex.get("vdda_min")
        if v is not None:
            vn = v / p["supply_v"]
            worst_vdda_min = vn if worst_vdda_min is None else min(worst_vdda_min, vn)
        if p["n_phase_ok"] != p["n_conversions"]:
            phase_ok = False
    return dict(
        arm=arm_name, n_points=len(mine), n_codes=total, n_moved=moved,
        n_unknown=unknown, max_abs_delta=max_abs, worst_gnd_pp_v=worst_gnd_pp,
        worst_vdda_min_frac=worst_vdda_min, phase_ok=phase_ok,
        n_missing=sum(1 for p in mine if p["missing"]),
    )


def controls(points: list[dict], control: dict | None) -> list[tuple[str, bool, str]]:
    """Mechanical checks a reader must see pass before trusting the table:
    (name, ok, detail)."""
    out: list[tuple[str, bool, str]] = []
    ideal = [p for p in points if p["arm"] == BASELINE_ARM]
    flat = all(
        p["extra"].get("gnd_die_max") is not None
        and abs(p["extra"]["gnd_die_max"]) < 1e-9
        and abs(p["extra"]["gnd_die_min"]) < 1e-9
        for p in ideal
    )
    out.append((
        "ideal arm: GND_DIE is exactly 0 V throughout",
        flat and bool(ideal),
        "the renamed analog ground, tied to 0 through a 0 V source, must not move",
    ))
    pkg = [p for p in points if ARMS_BY_NAME[p["arm"]].package and ARMS_BY_NAME[p["arm"]].gnd_pad]
    moves = all(
        p["extra"].get("gnd_die_max") is not None
        and (p["extra"]["gnd_die_max"] - p["extra"]["gnd_die_min"]) > 1e-4
        for p in pkg
    )
    out.append((
        "package arms: GND_DIE moves (> 0.1 mV p-p) at every point",
        moves and bool(pkg),
        "positive control -- the package network is actually in the circuit",
    ))
    if control is not None:
        base = next(
            (p for p in ideal if p["corner_id"] == control["corner_id"]), None
        )
        same = base is not None and codes(base) == codes(control)
        out.append((
            f"rename control: unrenamed as-committed deck at `{control['corner_id']}` "
            "gives the ideal arm's codes",
            same,
            f"unrenamed {codes(control)} vs ideal arm "
            f"{None if base is None else codes(base)}",
        ))
    missing = [f"{p['arm']}/{p['corner_id']}" for p in points if p["missing"]]
    out.append((
        "every measurement present at every point",
        not missing,
        "missing at: " + ", ".join(missing) if missing else "none missing",
    ))
    return out


# --------------------------------------------------------------------------
# Record
# --------------------------------------------------------------------------
def _v(x: float | None, scale: float = 1e3, fmt: str = ".1f") -> str:
    return "n/a" if x is None else format(x * scale, fmt)


def write_record(
    points: list[dict], control: dict | None, dut_text: str, arms: list[Arm], supersedes: str
) -> Path:
    raw = {f"{p['arm']}__{p['corner_id']}.log": p["log_text"] for p in points}
    if control is not None:
        raw[f"rename-control__{control['corner_id']}.log"] = control["log_text"]
    prov, lines = evidence.open_record(EXPERIMENT_DIR, dut_text, "corners", raw)
    # One representative assembled deck per arm (baseline corner), so the
    # exact network each arm ran is readable without re-running anything.
    deck_dir = EXPERIMENT_DIR / "corners" / prov.record_id / "decks"
    deck_dir.mkdir(parents=True, exist_ok=True)
    for p in points:
        if (p["process_corner"], p["temp_c"], p["supply_v"]) == fct.BASELINE_CORNER:
            (deck_dir / f"{p['arm']}__{p['corner_id']}.spice").write_text(p["deck"])

    processes = sorted({p["process_corner"] for p in points})
    temps = sorted({p["temp_c"] for p in points})
    supplies = sorted({p["supply_v"] for p in points})
    n_corners = len({p["corner_id"] for p in points})
    ctrl = controls(points, control)
    ctrl_ok = all(ok for _n, ok, _d in ctrl)
    summaries = [arm_summary(points, a.name) for a in arms]

    a = lines.append
    a(
        "- **Claim**: None against a `spec/target-spec.md` row -- no row names a "
        "supply-impedance tolerance and this record proposes none. This is the "
        "measurement DR-012 (`spec/decision-records/DR-012-analog-ground-pad.md`, "
        "issue #362) named as its open item and issue #378 tracks: the assembled "
        "`sar_adc_top` driven through package-like series R+L on its four supply "
        "terminals, and a LUMPED substrate-resistance stand-in, compared against "
        "the ideal-source case at the same PVT point. The substrate resistance is "
        "NOT an extraction (no substrate network exists in this repo) -- two "
        "bracketing values are run, and neither is claimed to be the physical one."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with two "
        "TESTBENCH-ONLY deck rewrites never written back to `design/`: the analog "
        "ground net `GND` renamed `GND_DIE` (ngspice aliases a node named `gnd` to "
        "the reference node 0, so it could not otherwise carry any series "
        "impedance), and the fragment's supply sources re-pointed through each "
        "arm's network. The snapshot below is the UNMODIFIED DUT; each arm's "
        f"assembled baseline-corner deck is kept under `corners/{prov.record_id}/decks/`."
    )
    a(
        corners_mod.corner_matrix_summary_line(processes, temps, supplies, n_corners)
        + f" -- per arm; {len(arms)} arms x {n_corners} points = {len(points)} "
        "transient runs" + (" + 1 rename-control run" if control is not None else "")
    )
    a(
        "- **Stimulus**: `sim/full-conversion-transient/`'s own, unmodified -- "
        f"`f_clk = {tb.F_CLK_HZ / 1e6:g} MHz`, {tb.N_CONVERSIONS} conversions of "
        f"{tb.PHASES_PER_CONVERSION} CLK periods, the first discarded, the rest "
        "carrying "
        + ", ".join(f"`{f:+.2f}*V_REF`" for f in tb.INPUT_FRACTIONS)
        + " (`testbench/full_conversion_tb_fragment.spice`, sha256 below)."
    )
    a(
        f"- **Package model**: one bond wire per supply terminal, "
        f"{BOND_WIRE_LENGTH_MM:g} mm x {BOND_WIRE_DIAMETER_UM:g} um Au: "
        f"`R = {R_PKG_OHM:g} ohm` (DC, rho = {GOLD_RESISTIVITY_OHM_M:g} ohm*m), "
        f"`L = {L_PKG_H * 1e9:.2f} nH` (isolated straight-wire self-inductance). "
        "Board side ideal: sources to node 0, no board impedance or decoupling. "
        "No on-die decoupling exists in this design (DR-010/DR-012 open item), so "
        "none is modelled. `VREFP`/`VREFN`/`VCM`, the inputs, `CLK` and `RST_B` "
        "stay ideal and board-referenced. Recorded as a stimulus assumption (not "
        "a package choice) in `spec/decision-records/DR-015-testbench-package-model.md`; "
        "derivation: `sim/ground-return-impedance/README.md`."
    )
    a(
        "- **Substrate stand-in**: `R_sub` in "
        + ", ".join(f"{r:g} ohm" for r in R_SUB_OHM)
        + " between `GND_DIE` and die-side `VGND` -- DR-012's measured fact that the "
        "two are ONE extracted net through the p-substrate, reduced to one "
        "resistor. No backside/paddle path is modelled (DR-012: nothing in this "
        "repo specifies one)."
    )
    runs = points + ([control] if control is not None else [])
    n_cached = sum(1 for r in runs if r.get("cached"))
    a(
        f"- **Raw-log reuse**: {n_cached} of {len(runs)} runs reused a raw ngspice log "
        "from `--cache-dir` (kept by an earlier invocation of the byte-identical deck "
        "on the same ngspice version and PDK revision); "
        f"{len(runs) - n_cached} were simulated by this invocation. Every raw log, "
        "reused or not, is committed under `corners/` below."
    )
    a(
        "- **Controls**: " + ("all pass" if ctrl_ok else "**FAIL -- read the Controls "
                              "table before any number below**")
    )
    a(
        "- **Result**: informational (no pass/fail row). Per-arm summary below; "
        "the quantity graded is each input's code change against the `ideal` arm "
        "at the same PVT point."
    )
    a("")

    a("## Arms")
    a("")
    a("| arm | package R+L | GND pad | R_sub (ohm) | what it isolates |")
    a("|---|---|---|---|---|")
    for arm in arms:
        a(
            f"| `{arm.name}` | {'yes' if arm.package else 'ideal'} | "
            f"{'bonded' if arm.gnd_pad else '**none**'} | "
            f"{'--' if arm.r_sub_ohm is None else f'{arm.r_sub_ohm:g}'} | {arm.what} |"
        )
    a("")

    a("## Controls")
    a("")
    a("| check | result | detail |")
    a("|---|---|---|")
    for name, ok, detail in ctrl:
        a(f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |")
    a("")

    a("## Per-arm summary (over every PVT point)")
    a("")
    a(
        "| arm | codes moved vs `ideal` | max \\|code change\\| (LSB) | "
        "worst GND_DIE p-p bounce (mV) | worst min v(VDD)-v(GND_DIE) (/ V_DD) | "
        "phase structure |"
    )
    a("|---|---|---|---|---|---|")
    for s in summaries:
        vd = "n/a" if s["worst_vdda_min_frac"] is None else f"{s['worst_vdda_min_frac']:.3f}"
        moved = f"{s['n_moved']}/{s['n_codes']}" + (
            f" ({s['n_unknown']} unreadable)" if s["n_unknown"] else ""
        )
        a(
            f"| `{s['arm']}` | {moved} | {s['max_abs_delta']} | "
            f"{s['worst_gnd_pp_v'] * 1e3:.1f} | {vd} | "
            f"{'OK' if s['phase_ok'] else 'WRONG somewhere'} |"
        )
    a("")

    a("## Captured codes, every arm at every PVT point")
    a("")
    a(
        "Each cell is `code (change vs ideal arm at the same point)`. Ideal codes "
        "for the five inputs: "
        + ", ".join(f"`{f:+.2f}*V_REF` -> {tb.ideal_code(f)}" for f in tb.INPUT_FRACTIONS)
        + ". The `ideal` arm's own error against those is the design's standing "
        "baseline (the near-full-scale inputs are issue #265/#267's known failure, "
        "not this campaign's); this campaign grades only the CHANGE."
    )
    a("")
    head = "| arm | corner-id | " + " | ".join(f"`{f:+.2f}`" for f in tb.INPUT_FRACTIONS) + " | phases |"
    a(head)
    a("|---|---" + "|---" * len(tb.INPUT_FRACTIONS) + "|---|")
    for arm in arms:
        for p in [q for q in points if q["arm"] == arm.name]:
            ds = code_deltas(p, baseline_for(points, p))
            cells = []
            for c, d in zip(codes(p), ds):
                if c is None:
                    cells.append("MISSING")
                elif arm.name == BASELINE_ARM:
                    cells.append(str(c))
                else:
                    cells.append(f"{c} ({'?' if d is None else f'{d:+d}'})")
            a(
                f"| `{arm.name}` | `{p['corner_id']}` | " + " | ".join(cells)
                + f" | {p['n_phase_ok']}/{p['n_conversions']} |"
            )
    a("")

    a("## Die-side bounce, every arm at every PVT point")
    a("")
    a(
        "All voltages against board ground (node 0), min/max over the five graded "
        "conversions. `VDDA` is `v(VDD) - v(GND_DIE)`, the analog supply the "
        "comparator and front end actually see. Currents are averages over "
        f"conversion {tb.IDD_CONVERSION}; `I(sub)` is the substrate stand-in's "
        "current from `GND_DIE` into `VGND`."
    )
    a("")
    a(
        "| arm | corner-id | GND_DIE min/max (mV) | VGND min/max (mV) | "
        "VDD min/max (V) | VPWR min/max (V) | VDDA min/max (V) | "
        "I(GND pad) (uA) | I(VGND pad) (uA) | I(sub) (uA) |"
    )
    a("|---|---|---|---|---|---|---|---|---|---|")
    for arm in arms:
        for p in [q for q in points if q["arm"] == arm.name]:
            ex = p["extra"]
            a(
                f"| `{arm.name}` | `{p['corner_id']}` | "
                f"{_v(ex.get('gnd_die_min'))} / {_v(ex.get('gnd_die_max'))} | "
                f"{_v(ex.get('vgnd_min'))} / {_v(ex.get('vgnd_max'))} | "
                f"{_v(ex.get('vdd_min'), 1, '.3f')} / {_v(ex.get('vdd_max'), 1, '.3f')} | "
                f"{_v(ex.get('vpwr_min'), 1, '.3f')} / {_v(ex.get('vpwr_max'), 1, '.3f')} | "
                f"{_v(ex.get('vdda_min'), 1, '.3f')} / {_v(ex.get('vdda_max'), 1, '.3f')} | "
                f"{_v(ex.get('i_vgnda'), 1e6, '.3f')} | {_v(ex.get('i_vgnd'), 1e6, '.3f')} | "
                f"{_v(ex.get('i_sub'), 1e6, '.3f')} |"
            )
    a("")

    a("## What this record can and cannot claim")
    a("")
    a(
        "- It CAN say whether, at this stimulus and these network values, any "
        "captured code moves when the ideal supply sources are replaced by the "
        "package/substrate networks above, and how far each die node bounces."
    )
    a(
        "- It CANNOT say what a real package or a real substrate does: the bond "
        "wire is one first-principles geometry (no mutual inductance between "
        "neighbouring wires, no package lead, no board), and `R_sub` is a single "
        "lumped resistor at two bracketing values, not an extracted substrate "
        "network. It also cannot speak to references: `VREFP`/`VREFN`/`VCM` "
        "stay ideal, and the CDAC's switching charge returns through `VREFN`, "
        "not through any of the four terminals graded here."
    )
    a(
        "- The stimulus is five DC inputs at one clock rate; a code that does not "
        "move here is not proof of immunity at other inputs or at a dynamic "
        "(sine) input."
    )
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns (max step; adaptive below it)",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per point",
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "reused deck assembly": "`sim/full-conversion-transient/run_conversion.py` "
                "(`assemble_deck`, `decode`), imported read-only",
            },
        )
    )
    a("")
    lines.extend(evidence.footer_lines(f"{RUNNER_REL} --corners --record", supersedes))
    path = evidence.close_record(prov, lines, "Record")
    (EXPERIMENT_DIR / "records" / "LATEST").write_text(f"{prov.record_id}.md\n")
    return path


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin")
    ap.add_argument("--corners", action="store_true", help="every arm over the ratified OAT grid (9 points)")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--arms", default=",".join(a.name for a in ARMS),
        help="comma-separated subset of arms (default: all). The `ideal` arm is "
        "always added, since every other arm is graded against it.",
    )
    ap.add_argument(
        "--no-rename-control", dest="rename_control", action="store_false",
        help="skip the unrenamed-deck control run (default: run it)",
    )
    ap.add_argument("--jobs", type=int, default=1, help="concurrent ngspice runs (runtime only)")
    ap.add_argument(
        "--supersedes", default="", metavar="RECORD_ID",
        help="record-id of a prior record of THIS experiment the new one replaces",
    )
    ap.add_argument(
        "--cache-dir", default="", metavar="DIR",
        help="keep each finished point's raw ngspice log here, and reuse one for a "
        "byte-identical deck on the same ngspice/PDK -- makes a long invocation "
        "resumable after a point exhausts its retries (runtime only)",
    )
    ap.add_argument("--list-arms", action="store_true", help="print the arms and exit")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.list_arms:
        print(f"package: R = {R_PKG_OHM:g} ohm, L = {L_PKG_H * 1e9:.3f} nH per bonded terminal")
        for arm in ARMS:
            print(f"  {arm.name:>16}  {arm.what}")
        return 0

    names = [n.strip() for n in args.arms.split(",") if n.strip()]
    unknown = [n for n in names if n not in ARMS_BY_NAME]
    if unknown:
        print(f"FAIL: unknown arm(s) {unknown}; see --list-arms", file=sys.stderr)
        return 2
    if BASELINE_ARM not in names:
        names.insert(0, BASELINE_ARM)
    arms = [a for a in ARMS if a.name in names]

    if args.supersedes and not (EXPERIMENT_DIR / "records" / f"{args.supersedes}.md").is_file():
        print(f"FAIL: --supersedes {args.supersedes}: no such record", file=sys.stderr)
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
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        return 1

    if tb.FRAGMENT_PATH.read_text() != tb.fragment_text():
        print("FAIL: the reused full-conversion fragment is stale.", file=sys.stderr)
        return 1

    n_pts = 9 if args.corners else 1
    print(
        f"Running {len(arms)} arm(s) x {n_pts} PVT point(s)"
        + (" + rename control" if args.rename_control else "")
        + f", {args.jobs} concurrent:"
    )
    with tempfile.TemporaryDirectory(prefix="ground-return-") as scratch_name:
        points, control, dut_text = run_campaign(
            arms, args.corners, args.jobs, args.quiet, Path(scratch_name), args.rename_control,
            Path(args.cache_dir).resolve() if args.cache_dir else None,
        )

    print("\nControls:")
    ctrl = controls(points, control)
    for name, ok, detail in ctrl:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} -- {detail}")
    print("\nPer-arm summary:")
    for arm in arms:
        s = arm_summary(points, arm.name)
        print(
            f"  {arm.name:>16}: moved {s['n_moved']}/{s['n_codes']}, max|d|={s['max_abs_delta']} LSB, "
            f"GND_DIE p-p {s['worst_gnd_pp_v'] * 1e3:.1f} mV, phases {'OK' if s['phase_ok'] else 'WRONG'}"
        )

    if args.record:
        write_record(points, control, dut_text, arms, args.supersedes)
    return 0 if all(ok for _n, ok, _d in ctrl) else 1


if __name__ == "__main__":
    raise SystemExit(main())

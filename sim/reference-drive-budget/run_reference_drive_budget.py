#!/usr/bin/env python3
"""Reference-drive impedance budget of the assembled ADC (issue #841).

    source sim/env.sh
    python3 sim/reference-drive-budget/run_reference_drive_budget.py --check-env
    python3 sim/reference-drive-budget/run_reference_drive_budget.py --probe
    python3 sim/reference-drive-budget/run_reference_drive_budget.py --record

WHAT THIS MEASURES. How much series source resistance `R_ref` the
`VREFP`/`VREFN` pads tolerate before the converter's captured output codes
move, at every ratified PVT corner. No `sim/` campaign put an impedance on
the reference before this one: `sim/supply-impedance-sensitivity/` says in
its own words that `VREFP`/`VREFN`/`VCM` "stay ideal at the die", and every
committed deck drives them from ideal DC sources with nothing in series. The
CDAC draws transient charge from the reference at every bit trial, so this is
the interface the "low resistance to the pad" question actually lands on.

WHY THE WHOLE ADC. The reference current is the charge the WHOLE array moves
when the SAR search flips bottom plates; a single-bit reduction holds the
other bits on ideal sources and so omits most of it. The DUT is therefore
`design/sar_adc_top.spice`, driven by `sim/full-conversion-transient/`'s own
committed stimulus/measurement fragment, used VERBATIM except for the two
reference source cards (see `patch_reference_sources()`), at the DR-023
reference solver policy. The observable is the captured code of each of the
five DC differential inputs.

THE CONTROL IS PER CORNER, NOT THE IDEAL CODE. Every corner carries its own
`R_ref = 0` row and every error is the code difference from THAT row. The
current full-conversion corner record resolves the three mid-scale inputs
within 1 LSB but is 100+ LSB off at `+-0.78*V_REF` at every corner (the
near-full-scale common-mode droop DR-021 proposes to fix). Referencing to
the ideal code would attribute that pre-existing, already-recorded defect to
the reference drive; referencing to the corner's own control does not.

BUDGET TIERS, adapted from `sim/vcm-drive-budget/`'s `find_budget()` to an
integer-code observable: the largest swept `R_ref` whose captured codes are
UNCHANGED from the control at every input (tier `0 LSB`), and the largest
whose codes move by at most 1 LSB (tier `1 LSB`). A budget equal to the
largest swept value is reported as right-censored, exactly as that campaign
reports it. `R_ref = 0` is simulated as ngspice's own zero-resistor floor
(it rewrites a 0 Ohm resistor to 1e-12 Ohm with a warning), which is what
makes the control row's topology identical to every other row's.

EXECUTION. The grid is ONE `klt sim` request: the ratified 9-point OAT PVT
set as `corners.process` x `corners.temperature_c`, the supply as the
`vdd_val` parameter axis (every source in the committed fragment is written
as an expression in `{vdd_val}`, so `corners.supply_v` -- which `alter`s a
source instance -- cannot move the rail, and klt refuses it for a PWL/PULSE
source anyway), and `R_ref` zipped against it as the second `corners.params`
name. `exclude` drops the full-factorial points the OAT star does not
contain. This script never loops `ngspice` itself; `--probe` runs ONE unit
through `klt sim --backend local`.

WHAT THE TESTBENCH DOES NOT MODEL. Series resistance only: no bond
inductance, no pad or bus capacitance, no decoupling network, no other
loading of any shared bus. `VCM` and all four supply terminals stay ideal at
the die. The inputs are DC (five levels, one conversion each) and the clock
is the DR-006 worst case `f_clk = 12 MHz` (`f_s = 1 MS/s`). A number from
this campaign is a statement about a series resistance on these two pads at
this conversion rate and nothing else.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent
#: This runner's repo-relative path, as the record's `Written by` footer and
#: `sim/spec-coverage.json`'s bench index must spell it.
RUNNER_REL = "sim/reference-drive-budget/run_reference_drive_budget.py"
SIM_DIR = EXPERIMENT_DIR.parent
FULL_CONVERSION_DIR = SIM_DIR / "full-conversion-transient"
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(FULL_CONVERSION_DIR))

from harness import corners as corners_mod, evidence  # noqa: E402

# The whole point of this campaign is to drive the EXISTING full-conversion
# stimulus, so that campaign's driver is imported and reused (its committed
# fragment, its code/phase decoding, its solver policy) rather than
# re-derived here. Nothing in that module is modified by this one -- the same
# read-in-place convention sim/supply-impedance-sensitivity/ already uses.
import run_conversion as fc  # noqa: E402

tb = fc.tb
REPO_ROOT = evidence.REPO_ROOT
DUT_NETLIST = REPO_ROOT / "design" / "sar_adc_top.spice"

NOMINAL_SUPPLY_V = fc.NOMINAL_SUPPLY_V
#: DR-023's reference transient solver policy -- the same card the cited
#: full-conversion corner record ran under, so the probe compares like with
#: like. Not a knob this campaign offers: a solver control is that campaign's
#: own mode (issue #637), not this one's.
SOLVER_PROFILE = fc.REFERENCE_SOLVER_PROFILE

#: Staged by `klt sim` from the worker's own PDK (the same spelling
#: sim/top-plate-cpar/ uses), never this host's absolute path.
STDCELL_INCLUDE = "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"
MODELS = {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"}

#: The two `corners.params` axis names. `vdd_val` is the fragment's own
#: supply parameter (it must stay the name the committed fragment reads);
#: `r_ref` is this campaign's.
VDD_PARAM = "vdd_val"
R_REF_PARAM = "r_ref"

#: Swept series resistance per reference pad, Ohm. `0` is the per-corner
#: control and `5` is the value Section 7 Item 11's route (iii) asks about,
#: so both are REQUIRED to be present (`check_r_values()`); above them a
#: x4 geometric ladder brackets the array's own RC -- one side is ~4.3 pF
#: (sim/top-plate-cpar/) against an 83.3 ns bit trial, so a 1-LSB-in-10-bit
#: settling error lands somewhere around 1e3 Ohm -- with a top rung far
#: enough above that to FAIL rather than censor every corner.
#:
#: LENGTH IS THE BINDING COST, not resolution: one unit is a whole-ADC 6.3 us
#: transient (485 s measured locally, tt/27C/1.80V), and the fleet kills a
#: whole JOB at 3600 s, so every extra rung is another 9 units and another
#: shard or two. Six rungs answer the question this campaign was filed for
#: (is 5 Ohm inside the tolerance, and where does the tolerance actually sit)
#: and bracket the budget to a factor of 4.
DEFAULT_R_OHM: tuple[float, ...] = (0.0, 5.0, 50.0, 200.0, 800.0, 3200.0)
CONTROL_R_OHM = 0.0
#: Values no sweep may omit: the control, and the figure the record must
#: speak to without interpolating.
REQUIRED_R_OHM: tuple[float, ...] = (0.0, 5.0)

#: The two committed fragment cards this campaign re-points, verbatim.
VREFP_CARD = "VVREFP VREFP 0 DC {vdd_val}"
VREFN_CARD = "VVREFN VREFN 0 DC 0"
VREFP_DRIVE_NODE = "VREFP_DRV"
VREFN_DRIVE_NODE = "VREFN_DRV"

#: Budget tiers, in LSB of captured-code movement from the corner's own
#: control row. Integer codes, so `0` is "no code moved at all".
TIER_LSB: tuple[float, ...] = (0.0, 1.0)

#: Per-UNIT kill (`options.timeout_s`). 2.5x the 485 s a tt/27C/1.80V unit
#: measured locally, so an ss/-40C unit has room without one stuck unit being
#: able to eat a whole shard's wall clock.
DEFAULT_TIMEOUT_S = 1200.0
#: Host rule: a batch submit waits for fleet capacity instead of failing the
#: step (the `--wait-for-capacity` the CLI passes, and the request's own
#: `batch.capacity_wait_s`).
DEFAULT_CAPACITY_WAIT_S = 600.0
#: Serial wall-clock budget allowed per unit when sizing shards. Deliberately
#: ABOVE the measured 485 s: the fleet's whole-job ceiling kills the job and
#: loses EVERY unit in it (not just the slow one), so the shard size is
#: computed as if the shard's units ran one after another, even though the
#: job actually runs them through `--backend local-parallel`.
SHARD_SERIAL_BUDGET_S = 600.0
#: The fleet's whole-job ceiling this sizing assumes (klt's own documented
#: fallback when the instance carries no `MaxJobSeconds` tag), minus the
#: 120 s of job overhead klt's own bound adds.
FLEET_JOB_CEILING_S = 3600.0
FLEET_JOB_OVERHEAD_S = 120.0


# --------------------------------------------------------------------------
# Deck assembly (pure; no PDK, no ngspice, no network)
# --------------------------------------------------------------------------
def split_fragment(fragment_text: str) -> tuple[str, list[str], str]:
    """Split the committed full-conversion fragment into the three pieces a
    `klt sim` request needs them in: the circuit BODY (sources only -- `klt
    sim` owns the `.control`/`.end` wrapper), the `.meas` cards (which become
    `measurements[].spice` entries), and the `.tran` card's arguments (which
    become `analysis.args`).

    Asserted rather than assumed: exactly one `.tran` card, and the `.meas`
    card names must be exactly the set `gen_full_conversion_tb.py` says it
    emits. A fragment that changes shape fails here instead of silently
    producing a deck that measures something else."""
    body: list[str] = []
    meas: list[str] = []
    tran_args: str | None = None
    for line in fragment_text.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith(".meas"):
            meas.append(stripped)
            continue
        if low.startswith(".tran"):
            if tran_args is not None:
                raise RuntimeError(
                    "expected exactly one .tran card in the committed fragment, found more "
                    "-- the fragment changed shape; re-derive this campaign."
                )
            tran_args = stripped.split(None, 1)[1].strip()
            continue
        body.append(line)
    if not tran_args:
        raise RuntimeError(
            "no .tran card found in the committed fragment -- the fragment changed shape; "
            "re-derive this campaign."
        )
    names = sorted(card.split()[2] for card in meas)
    expected = sorted(tb.all_measure_names())
    if names != expected:
        raise RuntimeError(
            f"committed fragment declares {len(names)} .meas cards, "
            f"gen_full_conversion_tb.all_measure_names() names {len(expected)}, and the two "
            "sets differ -- the fragment changed shape; re-derive this campaign."
        )
    return "\n".join(body) + "\n", meas, tran_args


def series_reference_lines() -> list[str]:
    return [
        "* --- issue #841: series source resistance on each reference pad ------",
        "* R_ref is the `r_ref` corners.params axis (Ohm), the same value on",
        "* both pads. At r_ref = 0 ngspice rewrites the card to its own 1e-12",
        "* Ohm floor (with a warning), so the control row's TOPOLOGY is",
        "* identical to every swept row's -- it is not a different deck.",
        f"RREFP {VREFP_DRIVE_NODE} VREFP {{{R_REF_PARAM}}}",
        f"RREFN {VREFN_DRIVE_NODE} VREFN {{{R_REF_PARAM}}}",
    ]


def patch_reference_sources(fragment_body: str) -> str:
    """Re-point the committed fragment's own `VVREFP`/`VVREFN` source cards
    at a drive-side node and put `R_ref` between them and the die.

    The source INSTANCE names are unchanged, so the fragment's own
    `.meas tran i_vrefp avg i(vvrefp)` cards still measure the current
    delivered from the drive side. Every other line of the fragment -- the
    clock, the reset, the input schedule, `VCM` and all four supply
    terminals -- is used verbatim."""
    text = fragment_body
    patched_refn = VREFN_CARD.replace(" VREFN 0 ", f" {VREFN_DRIVE_NODE} 0 ", 1)
    for old, new in (
        (VREFP_CARD, VREFP_CARD.replace(" VREFP 0 ", f" {VREFP_DRIVE_NODE} 0 ", 1)),
        (VREFN_CARD, patched_refn),
    ):
        if text.count(old) != 1:
            raise RuntimeError(
                f"expected exactly one `{old}` card in the committed fragment, found "
                f"{text.count(old)} -- the fragment changed shape; re-derive this campaign's "
                "reference re-pointing."
            )
        text = text.replace(old, new, 1)
    return text.replace(
        patched_refn, "\n".join([patched_refn, "", *series_reference_lines()]), 1
    )


def build_body(dut_text: str, fragment_text: str, *,
               stdcell_include: str = STDCELL_INCLUDE) -> str:
    """The circuit BODY `klt sim` wraps: no `.lib`, no `.temp`, no `.meas`,
    no `.tran`, no `.control`, no `.end` (see docs/cli/sim.md, "Netlist
    convention"). The corner's `.lib`/`.temp` cards and the analysis come
    from the request; `vdd_val` and `r_ref` are declared here because
    `corners.params` addresses an existing top-level `.param`."""
    frag_body, _meas, _tran = split_fragment(fragment_text)
    frag_body = patch_reference_sources(frag_body)
    dut_lines = [ln for ln in dut_text.splitlines() if ln.strip().lower() != ".end"]
    lines = [
        "* sim/reference-drive-budget -- VREFP/VREFN drive-impedance budget of",
        "* design/sar_adc_top.spice (issue #841). Assembled by",
        f"* {RUNNER_REL}.",
        "* Circuit body only: klt sim supplies the .lib corner section, .temp,",
        "* the .meas cards, the .tran analysis and the .control wrapper.",
        "* The stimulus/measurement fragment is sim/full-conversion-transient's,",
        "* used verbatim except for the two reference source cards.",
        f".param {VDD_PARAM} = {NOMINAL_SUPPLY_V:g}",
        f".param {R_REF_PARAM} = {CONTROL_R_OHM:g}",
        f".include {stdcell_include}",
        "* VPWR/VGND have no schematic-graph node inside sar_sequencer (see",
        "* design/sar_adc_top.sch's header); the testbench ties them here.",
        ".global VPWR VGND",
        "",
        *dut_lines,
        "",
        frag_body,
        *fc.solver_profile_deck_lines(SOLVER_PROFILE),
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# `klt sim` request
# --------------------------------------------------------------------------
_CURRENT_MEAS = {name for name, _src, _pot in tb.SUPPLY_SOURCES}
_VECTOR_RE = re.compile(r"\b([vi])\(([^)]+)\)", re.IGNORECASE)


def measurement_entries(meas_cards: list[str]) -> list[dict]:
    """One `measurements[].spice` entry per committed `.meas` card, name and
    card text unchanged. `klt sim` requires the card's name to equal the
    measurement name, which the fragment already satisfies."""
    out = []
    for card in meas_cards:
        name = card.split()[2]
        out.append({"name": name, "spice": card,
                    "unit": "A" if name in _CURRENT_MEAS else "V"})
    return out


def saved_vectors(meas_cards: list[str]) -> list[str]:
    """Exactly the vectors the `.meas` cards read, so a 6.3 us transient over
    ~2000 devices does not carry a `save all` rawfile per unit."""
    found = set()
    for card in meas_cards:
        for kind, node in _VECTOR_RE.findall(card):
            found.add(f"{kind.lower()}({node.strip().lower()})")
    return sorted(found)


def ratified_points() -> list[tuple[str, float, float]]:
    """The ratified 9-point one-at-a-time PVT star (sim/harness/corners.py)."""
    return corners_mod.ratified_oat_grid(
        NOMINAL_SUPPLY_V,
        corners_mod.RATIFIED_SUPPLY_TOLERANCE,
        corners_mod.RATIFIED_PROCESS_CORNERS,
        corners_mod.RATIFIED_TEMPS_C,
    )


def normalize_r_values(r_values: list[float]) -> list[float]:
    """Sorted, de-duplicated, non-negative. Shape only -- the campaign-level
    requirement that `0` and `5` are present is `check_r_values()`."""
    vals = sorted(set(float(r) for r in r_values))
    if not vals:
        raise ValueError("the swept R_ref list is empty")
    if vals[0] < 0:
        raise ValueError(f"R_ref values must be >= 0, got {vals[0]}")
    return vals


def check_r_values(r_values: list[float]) -> list[float]:
    """normalize_r_values() plus the campaign's own requirement: a recorded
    sweep must carry the per-corner control AND the figure the record has to
    speak to, so neither is ever reached by interpolation."""
    vals = normalize_r_values(r_values)
    missing = [r for r in REQUIRED_R_OHM if r not in vals]
    if missing:
        raise ValueError(
            f"a recorded R_ref sweep must contain {list(REQUIRED_R_OHM)} Ohm "
            "(the per-corner control, and the figure the record must state without "
            f"interpolating); missing {missing}"
        )
    return vals


def shard_count(n_units: int, *, serial_budget_s: float = SHARD_SERIAL_BUDGET_S,
                ceiling_s: float = FLEET_JOB_CEILING_S,
                overhead_s: float = FLEET_JOB_OVERHEAD_S) -> int:
    """How many batch jobs (`remote.hosts`) this grid needs so that each
    shard fits the fleet's whole-job ceiling even if its units ran SERIALLY.

    Why an explicit `remote.hosts` rather than `batch.job_ceiling_check:
    "split"`: the automatic split sizes shards from `options.timeout_s`, the
    per-unit KILL, which is deliberately 2.5x the measured runtime -- that
    would shard this grid into two-unit jobs. An explicit `hosts` is honored
    as given and its shards are not assessed (docs/cli/sim.md, "Three
    budgets"), so the sizing can use the MEASURED runtime instead. It stays
    conservative in the direction that matters: a job killed at the ceiling
    loses every unit in it, including the ones that had finished."""
    per_shard = max(1, int((ceiling_s - overhead_s) // serial_budget_s))
    return max(1, -(-n_units // per_shard))


def build_request(
    netlist_name: str,
    points: list[tuple[str, float, float]],
    r_values: list[float],
    meas_cards: list[str],
    tran_args: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    backend: str | None = None,
    capacity_wait_s: float | None = None,
    hosts: int | None = None,
) -> dict:
    """ONE request covering exactly `points` x `r_values`.

    The PVT star is the cross product of its distinct process and temperature
    values with the points it does not contain removed by `exclude`; the
    supply is a `corners.params` row rather than a `corners.supply_v` axis
    because every source in the committed fragment reads `{vdd_val}` and
    `alter` addresses instances, never a `.param` (docs/cli/sim.md, "Corner
    axes"). `R_ref` zips against the supply in the same rows, so the rows are
    the full supply x R_ref product and the expansion is
    process x temperature x row."""
    r_values = normalize_r_values(r_values)
    procs = sorted({p for p, _, _ in points})
    temps = sorted({t for _, t, _ in points})
    vdds = sorted({v for _, _, v in points})
    rows = [(v, r) for v in vdds for r in r_values]
    want = set(points)
    exclude = [
        {"process": p, "temperature_c": t, "params": {VDD_PARAM: v}}
        for p in procs
        for t in temps
        for v in vdds
        if (p, t, v) not in want
    ]
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": dict(MODELS),
        "corners": {
            "process": procs,
            "temperature_c": temps,
            "params": {
                VDD_PARAM: [v for v, _ in rows],
                R_REF_PARAM: [r for _, r in rows],
            },
        },
        "analysis": {"kind": "tran", "args": tran_args},
        "measurements": measurement_entries(meas_cards),
        "options": {
            "timeout_s": timeout_s,
            "keep_artifacts": True,
            "save_vectors": saved_vectors(meas_cards),
        },
    }
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    if hosts and hosts > 1:
        req["remote"] = {"hosts": hosts}
    if capacity_wait_s is not None:
        req["batch"] = {"capacity_wait_s": capacity_wait_s}
    return req


# --------------------------------------------------------------------------
# Report reading (refuses an error envelope rather than inventing numbers)
# --------------------------------------------------------------------------
@dataclass
class UnitResult:
    process: str
    temp_c: float
    supply_v: float
    r_ohm: float
    status: str
    values: dict[str, float | None]
    errors: list[str] = field(default_factory=list)

    @property
    def point(self) -> tuple[str, float, float]:
        return (self.process, self.temp_c, self.supply_v)

    @property
    def usable(self) -> bool:
        return self.status not in ("error", "inconclusive") and not self.errors


def read_report(report: dict) -> tuple[dict[tuple, UnitResult], dict]:
    """`{(process, temp_c, supply_v, r_ohm): UnitResult}` plus run info.

    Raises on an error envelope or a report with no `corners[]`: a campaign
    stops on those rather than reporting a budget it did not measure."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {json.dumps(report['error'])}")
    corners = report.get("corners")
    if not isinstance(corners, list):
        raise ValueError("klt sim report has no corners[] list")
    out: dict[tuple, UnitResult] = {}
    for c in corners:
        params = c.get("params") or {}
        if VDD_PARAM not in params or R_REF_PARAM not in params:
            raise ValueError(
                f"corner {c.get('corner_id')!r} echoes no {VDD_PARAM}/{R_REF_PARAM} params -- "
                "the worker image does not implement corners.params; no result is read from it."
            )
        unit = UnitResult(
            process=str(c.get("process")),
            temp_c=float(c["temperature_c"]),
            supply_v=float(params[VDD_PARAM]),
            r_ohm=float(params[R_REF_PARAM]),
            status=str(c.get("status")),
            values={
                m["name"]: m.get("value")
                for m in (c.get("measurements") or [])
                if isinstance(m, dict) and "name" in m
            },
            errors=[
                str(d.get("code"))
                for d in (c.get("diagnostics") or [])
                if isinstance(d, dict) and d.get("severity") == "error"
            ],
        )
        key = (unit.process, unit.temp_c, unit.supply_v, unit.r_ohm)
        if key in out:
            raise ValueError(f"klt sim report has two corners at {key}")
        out[key] = unit
    env = report.get("environment") or {}
    remote = env.get("remote") or {}
    return out, run_info(report, remote)


def _ngspice_from_banner(banner: str) -> str | None:
    for line in (banner or "").splitlines():
        token = next((t for t in line.replace("*", " ").split() if t.startswith("ngspice-")), None)
        if token:
            return token.strip(":,")
    return None


def run_info(report: dict, remote: dict) -> dict:
    """Run-level facts, from EITHER batch report shape.

    A one-job batch run carries `job_id` and `worker_environment` directly on
    `environment.remote`; a SHARDED run (`remote.hosts > 1`, which this
    campaign always uses) carries one entry per shard under
    `environment.remote.fleet[]` instead, and the single-job keys are absent.
    Reading only the single-job shape is how a sharded record ends up
    reporting `job None` -- so both are handled here, and the executing
    PDK/simulator are only reported when EVERY shard agrees on them."""
    shards = remote.get("fleet")
    entries = shards if isinstance(shards, list) and shards else [remote]
    jobs = []
    pdks, ngs, features = set(), set(), set()
    for entry in entries:
        worker = entry.get("worker_environment") or {}
        pdk_stamp = (worker.get("pdk") or {}).get("stamp_text")
        variant = (worker.get("pdk") or {}).get("variant")
        ng = _ngspice_from_banner((worker.get("simulator") or {}).get("version_banner") or "")
        if pdk_stamp:
            pdks.add(f"{variant} @ {pdk_stamp.split()[-1]}" if variant else pdk_stamp)
        if ng:
            ngs.add(ng)
        feats = entry.get("runner_request_features") or {}
        if feats.get("status"):
            features.add(str(feats["status"]))
        if entry.get("job_id"):
            jobs.append({
                "job_id": entry.get("job_id"),
                "state": entry.get("state"),
                "exit_code": entry.get("exit_code"),
                "instance_type": entry.get("instance_type"),
                "elapsed_seconds": entry.get("elapsed_seconds"),
                "runner_klt_version": entry.get("runner_klt_version"),
            })
    backend = (report.get("environment") or {}).get("backend")
    if isinstance(backend, dict):
        backend = backend.get("resolved") or backend.get("requested")
    return {
        "status": report.get("status"),
        "jobs": jobs,
        "job_id": jobs[0]["job_id"] if len(jobs) == 1 else None,
        "sharded": bool(isinstance(shards, list) and shards),
        "remote": remote or None,
        "resolved_backend": backend,
        # Only when every shard agrees; a mixed fleet reports None rather than
        # letting one shard's environment stand for the whole run.
        "worker_pdk": next(iter(pdks)) if len(pdks) == 1 else None,
        "worker_ngspice": next(iter(ngs)) if len(ngs) == 1 else None,
        "worker_pdks_seen": sorted(pdks),
        "worker_ngspice_seen": sorted(ngs),
        "request_feature_status": next(iter(features)) if len(features) == 1 else None,
    }


# --------------------------------------------------------------------------
# Analysis: per-corner rows, deltas against that corner's own control, tiers
# --------------------------------------------------------------------------
def decode_unit(unit: UnitResult) -> dict:
    """Captured codes + phase verdicts for one unit, using the full-conversion
    campaign's own decoder (same threshold, same MSB-first bit order)."""
    stream = fc.decode_code_stream(unit.values, unit.supply_v, tb.measured_conversions())
    codes = stream["codes"]
    return {
        "r_ohm": unit.r_ohm,
        "status": unit.status,
        "errors": list(unit.errors),
        "codes": codes,
        "phase_ok": stream["phase_ok"],
        "all_phase_ok": all(stream["phase_ok"]),
        "complete": unit.usable and all(c is not None for c in codes),
        "i_vrefp_a": unit.values.get("i_vrefp"),
        "i_vrefn_a": unit.values.get("i_vrefn"),
    }


def apply_control(rows: list[dict]) -> list[dict]:
    """Attach each row's code deltas against the `R_ref = 0` row of the SAME
    corner. Rows are returned sorted by `r_ohm`. `deltas`/`max_abs_delta` are
    None wherever the control or the row itself is incomplete -- never zero,
    which would read as "no movement"."""
    rows = sorted(rows, key=lambda r: r["r_ohm"])
    control = next((r for r in rows if r["r_ohm"] == CONTROL_R_OHM), None)
    for row in rows:
        row["is_control"] = control is not None and row is control
        if control is None or not control["complete"] or not row["complete"]:
            row["deltas"] = None
            row["max_abs_delta"] = None
            continue
        deltas = [c - b for c, b in zip(row["codes"], control["codes"], strict=True)]
        row["deltas"] = deltas
        row["max_abs_delta"] = max(abs(d) for d in deltas)
    return rows


def find_budget(rows: list[dict], threshold_lsb: float) -> dict | None:
    """The largest swept `R_ref` whose code movement from the control stays
    within `threshold_lsb` -- None if not even the control row is usable.

    Same selection rule as `sim/vcm-drive-budget/`'s `find_budget()`: the
    LAST passing row in ascending order, not the last row before the first
    failure. `monotone` on the returned dict says whether any row above the
    budget also passed (it should not, and the record says so when it does)."""
    ok = [r for r in rows if r["max_abs_delta"] is not None
          and r["max_abs_delta"] <= threshold_lsb]
    if not ok:
        return None
    best = ok[-1]
    first_fail = next((r for r in rows if r["max_abs_delta"] is None
                       or r["max_abs_delta"] > threshold_lsb), None)
    return {
        "r_ohm": best["r_ohm"],
        "censored": best["r_ohm"] == rows[-1]["r_ohm"],
        "monotone": first_fail is None or first_fail["r_ohm"] > best["r_ohm"],
    }


def analyze(units: dict[tuple, UnitResult], points: list[tuple[str, float, float]],
            r_values: list[float]) -> dict:
    """Per-corner rows, budgets and completeness. A missing unit is reported
    as missing; it is never treated as a pass."""
    out: dict[tuple, dict] = {}
    for point in points:
        rows = []
        missing = []
        for r in r_values:
            unit = units.get((point[0], point[1], point[2], r))
            if unit is None:
                missing.append(r)
                rows.append({"r_ohm": r, "status": "missing", "errors": [], "codes":
                             [None] * len(tb.measured_conversions()), "phase_ok": [],
                             "all_phase_ok": False, "complete": False,
                             "i_vrefp_a": None, "i_vrefn_a": None})
                continue
            rows.append(decode_unit(unit))
        rows = apply_control(rows)
        control = next((r for r in rows if r["r_ohm"] == CONTROL_R_OHM), None)
        out[point] = {
            "corner_id": corners_mod.corner_id(*point),
            "rows": rows,
            "missing_r": missing,
            "control_complete": bool(control and control["complete"]),
            "control_codes": control["codes"] if control else None,
            "control_ideal_match": (
                control["codes"] == ideal_codes() if control and control["complete"] else None
            ),
            "budgets": {
                tier: find_budget(rows, tier) for tier in TIER_LSB
            },
            "complete": all(r["complete"] for r in rows),
        }
    return out


def ideal_codes() -> list[int]:
    return [tb.ideal_code(tb.input_fraction(c)) for c in tb.measured_conversions()]


# --------------------------------------------------------------------------
# Submission -- every simulation unit goes through `klt sim`
# --------------------------------------------------------------------------
class SubmitError(RuntimeError):
    pass


def submit(points: list[tuple[str, float, float]], r_values: list[float], workdir: Path,
           *, backend: str | None, timeout_s: float, capacity_wait_s: float | None,
           hosts: int | None, tag: str = "grid",
           ) -> tuple[dict[tuple, UnitResult], dict, dict]:
    """Write the deck + request under `workdir/<tag>/`, submit it through
    `klt sim`, and read the report back. An existing `report.json` is reused,
    so a re-run after a collection failure does not re-simulate."""
    d = workdir / tag
    d.mkdir(parents=True, exist_ok=True)
    fragment_text = tb.FRAGMENT_PATH.read_text()
    _body, meas_cards, tran_args = split_fragment(fragment_text)
    (d / "tb.spice").write_text(build_body(DUT_NETLIST.read_text(), fragment_text))
    req = build_request(
        "tb.spice", points, r_values, meas_cards, tran_args,
        timeout_s=timeout_s, backend=backend, capacity_wait_s=capacity_wait_s,
        hosts=hosts,
    )
    (d / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    rep_path = d / "report.json"
    if rep_path.is_file():
        report = json.loads(rep_path.read_text())
    else:
        argv = ["klt", "sim", str(d / "request.json"), "--format", "json",
                "-o", str(d / "out")]
        if backend:
            argv += ["--backend", backend]
        if backend != "local" and capacity_wait_s is not None:
            argv += ["--wait-for-capacity", f"{capacity_wait_s:g}"]
        print(f"[{tag}] {' '.join(argv)}", flush=True)
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
        try:
            report = json.loads(done.stdout)
        except json.JSONDecodeError:
            try:
                report = json.loads(done.stderr)
            except json.JSONDecodeError as exc:
                raise SubmitError(
                    f"klt sim ({tag}) returned no JSON report (rc={done.returncode}): "
                    f"{(done.stderr or done.stdout)[:1200]}"
                ) from exc
        if "error" in report and "corners" not in report:
            raise SubmitError(f"klt sim ({tag}): {json.dumps(report['error'])}")
        rep_path.write_text(json.dumps(report, indent=1) + "\n")
    units, info = read_report(report)
    info = dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)")
    return units, info, req


# --------------------------------------------------------------------------
# Record
# --------------------------------------------------------------------------
def _ohm(r: float) -> str:
    return f"{r:g}"


def _ua(a: float | None) -> str:
    return "n/a" if a is None else f"{a * 1e6:+.3f}"


#: The committed full-conversion corner record's own power table, read at
#: write time (never a number transcribed into this file, so a later re-run of
#: that campaign cannot leave a stale figure here -- the same convention
#: `run_conversion.behavioral_enob_reference()` uses).
FULL_CONVERSION_RECORDS = FULL_CONVERSION_DIR / "records"


def full_conversion_reference(records_dir: Path = FULL_CONVERSION_RECORDS
                              ) -> tuple[str, dict[str, float]] | None:
    """`(record-id, {corner_id: I(VREFP) in amps})` from
    `sim/full-conversion-transient/records/LATEST`, or None when that record
    is unavailable or carries no power table.

    That campaign drives the SAME DUT with the SAME fragment from IDEAL
    reference sources, so its `I(VREFP)` is what this campaign's swept rows
    should converge to as `R_ref` falls -- an independent check that the
    re-pointed sources drive the same circuit. The column is located by its
    header name, not by position."""
    latest = records_dir / "LATEST"
    if not latest.is_file():
        return None
    record = records_dir / latest.read_text().strip()
    if not record.is_file():
        return None
    col = None
    out: dict[str, float] = {}
    for line in record.read_text().splitlines():
        if not line.startswith("|"):
            col = None if out else col
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if col is None:
            if any(c.startswith("I(VREFP)") for c in cells):
                col = next(i for i, c in enumerate(cells) if c.startswith("I(VREFP)"))
            continue
        if len(cells) <= col or set(cells[0]) <= set("-: "):
            continue
        try:
            out[cells[0].strip("`")] = float(cells[col]) * 1e-6
        except ValueError:
            continue
    return (record.stem, out) if out else None


def _budget_cell(b: dict | None) -> str:
    if b is None:
        return "none (control unusable)"
    cell = f"{_ohm(b['r_ohm'])} Ohm"
    if b["censored"]:
        cell += " (right-censored)"
    if not b["monotone"]:
        cell += " (non-monotone)"
    return cell


def interpretation_lines(analysis: dict, points: list, r_values: list[float]) -> list[str]:
    """The `5 Ohm` statement the issue asks for, stated only as far as the
    rows support it."""
    five = 5.0
    complete = [p for p in points if analysis[p]["control_complete"]]
    rows_at_5 = {
        analysis[p]["corner_id"]: next(
            (r for r in analysis[p]["rows"] if r["r_ohm"] == five), None)
        for p in complete
    }
    readable = {cid: r for cid, r in rows_at_5.items()
                if r is not None and r["max_abs_delta"] is not None}
    worst = max((r["max_abs_delta"] for r in readable.values()), default=None)
    lines = [
        "## Is `less than 5 ohms` in series inside the tolerance?",
        "",
    ]
    if not readable:
        lines += [
            f"**Not readable.** No corner produced a usable `R_ref = {_ohm(five)}` Ohm row "
            "against a usable control, so this record states nothing about 5 Ohm.",
        ]
        return lines
    inside = worst is not None and worst <= 1.0
    lines += [
        f"- `{_ohm(five)}` Ohm is a SIMULATED point of this sweep at "
        f"{len(readable)}/{len(points)} corners -- not an interpolation between swept values.",
        f"- Worst captured-code movement from the same corner's own `R_ref = 0` control, "
        f"over those corners and all {len(tb.measured_conversions())} inputs: "
        f"**{worst} LSB**.",
        (
            f"- On that evidence a series resistance below `{_ohm(five)}` Ohm on each reference "
            "pad is INSIDE the tolerance this campaign measures"
            if inside else
            f"- On that evidence a series resistance of `{_ohm(five)}` Ohm on each reference pad "
            "is OUTSIDE the 1 LSB tier at at least one corner"
        )
        + " -- for a pure series resistance, at this conversion rate, with nothing else on "
        "the net.",
        "",
        "**This says nothing about a shared analog bus.** The testbench models two "
        "resistors. It does not model the other loading such a bus would carry (the "
        "other projects sharing it, their switching activity, or any high-frequency "
        "behaviour), nor bus/pad capacitance, nor inductance, nor a decoupling network. "
        "A bus whose switch resistance happens to be under 5 Ohm is not thereby shown to "
        "be usable here; only the series-resistance term of it is addressed.",
    ]
    return lines


def _control_i_vrefp(corner_analysis: dict) -> float | None:
    return next((r["i_vrefp_a"] for r in corner_analysis["rows"]
                 if r["r_ohm"] == CONTROL_R_OHM), None)


def reference_current_lines(analysis: dict, points: list, r_values: list[float]) -> list[str]:
    """The averaged reference current: what it validates, and the one place
    it is NOT readable.

    Two separate statements, both computed here rather than asserted:

    1. **The swept rows reproduce the committed full-conversion record.** That
       campaign drives the same DUT with the same fragment from IDEAL
       reference sources; if the re-pointed sources plus `R_ref` drive the
       same circuit, the swept rows' `|avg i(VREFP)|` must land on its
       `I(VREFP)` at the corners the two campaigns share.
    2. **The `R_ref = 0` row's current is not readable.** At `R_ref = 0` the
       series element is ngspice's 1e-12 Ohm floor, so the branch current is
       ill-conditioned by construction. The captured CODES -- the observable
       every budget in this record is computed from -- are unaffected, which
       the control-vs-swept code columns above show directly.
    """
    swept = [r for r in r_values if r != CONTROL_R_OHM]
    lines = ["## Averaged reference current: cross-check, and the control row's `(*)`", ""]

    ref = full_conversion_reference()
    if ref is None:
        lines += [
            "**Cross-check not run.** `sim/full-conversion-transient/records/LATEST` "
            "could not be read, so this record states no comparison with the "
            "ideal-source campaign.",
            "",
        ]
    else:
        rec_id, ideal_i = ref
        lines += [
            f"Against `sim/full-conversion-transient/records/{rec_id}.md` -- the same DUT "
            "and the same fragment driven from IDEAL reference sources. This campaign's "
            "swept rows should land on that record's `I(VREFP)` (which reports "
            "magnitudes; the sign convention below is ngspice's own, current out of the "
            "source's positive terminal).",
            "",
            "| corner | ideal-source record I(VREFP) (uA) | this run, "
            + ", ".join(f"{_ohm(r)} Ohm" for r in swept)
            + " (uA) | worst abs difference (uA) |",
            "|---|---|---|---|",
        ]
        worst_overall = None
        for p in points:
            a = analysis[p]
            cid = a["corner_id"]
            if cid not in ideal_i:
                continue
            mags = [(r["r_ohm"], abs(r["i_vrefp_a"])) for r in a["rows"]
                    if r["r_ohm"] != CONTROL_R_OHM and r["i_vrefp_a"] is not None]
            if not mags:
                continue
            diffs = [abs(v - ideal_i[cid]) for _r, v in mags]
            worst = max(diffs)
            worst_overall = worst if worst_overall is None else max(worst_overall, worst)
            lines.append(
                f"| `{cid}` | {ideal_i[cid] * 1e6:.3f} | "
                + ", ".join(f"{v * 1e6:.3f}" for _r, v in mags)
                + f" | {worst * 1e6:.3f} |"
            )
        if worst_overall is not None:
            lines += [
                "",
                f"Worst difference over every corner the two campaigns share and every "
                f"swept value: **{worst_overall * 1e6:.3f} uA**. The swept rows therefore "
                "reproduce the ideal-source campaign's reference current, which is "
                "evidence that re-pointing `VVREFP`/`VVREFN` through `R_ref` drives the "
                "same circuit rather than a differently-wired one.",
            ]
        else:
            lines += ["", "No corner is shared with that record's power table, so no "
                      "comparison is stated."]

    lines += [
        "",
        "**`(*)` -- the `R_ref = 0` row's current cells are NOT a measurement.** At "
        "`R_ref = 0` the series element is ngspice's own 1e-12 Ohm resistor floor, so "
        "`avg i(vvrefp)` across that near-short is numerically ill-conditioned. In this "
        "run it comes back two to three orders of magnitude away from every swept row, "
        "and its SIGN is not even consistent from corner to corner -- "
        + "; ".join(
            f"`{analysis[p]['corner_id']}` {_ua(_control_i_vrefp(analysis[p]))}"
            for p in points if _control_i_vrefp(analysis[p]) is not None
        )
        + " uA -- which is what an ill-conditioned branch looks like, not a reference "
        "current. The values are printed because they are in the raw report either way; "
        "they are marked so they cannot be read as measurements.",
        "",
        "**No budget in this record depends on them.** Every budget is computed from the "
        "captured CODES, and the control row's codes are sound: they are identical to "
        "the adjacent swept rows at every corner (see the table above), and at "
        "`tt_27c_1.80v` they match the committed full-conversion record's captured codes "
        "for that corner exactly. The reference-current column is reported alongside the "
        "codes, not used by the tiers.",
    ]
    return lines


def write_record(analysis: dict, points: list, r_values: list[float], info: dict,
                 req: dict, workdir: Path, supersedes: str, tag: str = "grid") -> Path:
    body = build_body(DUT_NETLIST.read_text(), tb.FRAGMENT_PATH.read_text())
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, body, "corners",
        {"report.json": (workdir / tag / "report.json").read_text()},
    )
    record_dir = EXPERIMENT_DIR / "corners" / prov.record_id
    (record_dir / "request.json").write_text((workdir / tag / "request.json").read_text())
    (record_dir / "tb.spice").write_text((workdir / tag / "tb.spice").read_text())

    complete = [p for p in points if analysis[p]["complete"]]
    ideal = ideal_codes()
    n_units = len(points) * len(r_values)
    lines += [
        "- **Claim**: none -- characterization. Measures how much series source "
        "resistance the `VREFP`/`VREFN` pads tolerate; `spec/target-spec.md` is "
        "untouched (DRAFT until #1) and no route of Section 7 Item 11 is chosen.",
        "- **Issue**: #841",
        "- **DUT**: `design/sar_adc_top.spice` as committed at the `git` commit named in "
        "Environment below, driven by `sim/full-conversion-transient/testbench/"
        "full_conversion_tb_fragment.spice` used verbatim except for the two reference "
        "source cards (`VVREFP`/`VVREFN` re-pointed to a drive node, `R_ref` in series "
        "to the die). `VCM`, `VDD`, `VPWR` and `VGND` stay ideal at the die.",
        f"- **Observable**: the captured output code of each of the "
        f"{len(tb.measured_conversions())} DC differential inputs, read mid-`PH_EOC`, "
        "compared with the SAME corner's own `R_ref = 0` control row -- never with the "
        "ideal code.",
        f"- **Sweep**: `R_ref` = {', '.join(_ohm(r) for r in r_values)} Ohm on each pad "
        f"(same value on both), at each of {len(points)} ratified PVT corners "
        f"({n_units} simulation units in one `klt sim` request).",
        corners_mod.corner_matrix_summary_line(
            sorted({p for p, _, _ in points}),
            sorted({t for _, t, _ in points}),
            sorted({v for _, _, v in points}),
            len(points),
        ),
        f"- **Budget tiers**: largest swept `R_ref` whose captured codes move by at most "
        f"{', '.join(f'{t:g}' for t in TIER_LSB)} LSB from that corner's control. A budget "
        "equal to the largest swept value is reported as right-censored "
        "(`sim/vcm-drive-budget/`'s convention).",
        f"- **Corners**: {len(complete)}/{len(points)} complete at every swept value",
        "- **Overall**: " + ("COMPLETE" if len(complete) == len(points) else "INCOMPLETE"),
        "",
        "## Tolerable reference source resistance per corner",
        "",
        "| corner | control `R_ref = 0` usable | control codes == ideal | "
        + " | ".join(f"budget, {t:g} LSB tier" for t in TIER_LSB)
        + " | rows complete |",
        "|---|---|---|" + "---|" * (len(TIER_LSB) + 1),
    ]
    for p in points:
        a = analysis[p]
        lines.append(
            f"| `{a['corner_id']}` | {'yes' if a['control_complete'] else 'NO'} | "
            + ("yes" if a["control_ideal_match"] else
               ("no" if a["control_ideal_match"] is False else "n/a"))
            + " | "
            + " | ".join(_budget_cell(a["budgets"][t]) for t in TIER_LSB)
            + f" | {sum(1 for r in a['rows'] if r['complete'])}/{len(r_values)} |"
        )
    lines += [
        "",
        "`control codes == ideal` is context, not a criterion: the committed "
        "full-conversion corner record already reports that the two `+-0.78*V_REF` inputs "
        "miss their ideal code by 100+ LSB at every corner (the near-full-scale droop "
        "DR-021 proposes to fix). Every budget above is measured against the control row, "
        "so that pre-existing error is in both sides of the comparison and is not "
        "attributed to the reference drive.",
        "",
        "## Captured codes and movement from the control, per corner and swept value",
        "",
        "Ideal codes for the five inputs ("
        + ", ".join(f"{tb.input_fraction(c):+.2f}*V_REF" for c in tb.measured_conversions())
        + f"): {ideal}. `delta` is captured minus the SAME corner's `R_ref = 0` row.",
        "",
        "| corner | R_ref (Ohm) | codes | delta vs control | max abs delta (LSB) | "
        "phase structure | avg i(VREFP) (uA) | avg i(VREFN) (uA) | status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in points:
        a = analysis[p]
        for row in a["rows"]:
            codes = ", ".join("n/a" if c is None else str(c) for c in row["codes"])
            deltas = ("n/a" if row["deltas"] is None
                      else ", ".join(f"{d:+d}" for d in row["deltas"]))
            md = "n/a" if row["max_abs_delta"] is None else str(row["max_abs_delta"])
            phase = ("ok" if row["all_phase_ok"] else
                     ("FAIL" if row["complete"] else "n/a"))
            # At R_ref = 0 the series element IS ngspice's 1e-12 Ohm floor, so
            # the branch current through it is ill-conditioned BY CONSTRUCTION.
            # The value is still printed (it is in report.json either way) but
            # is marked so it cannot be read as a measurement.
            mark = " (*)" if row["r_ohm"] == CONTROL_R_OHM else ""
            lines.append(
                f"| `{a['corner_id']}` | {_ohm(row['r_ohm'])}"
                + (" (control)" if row["r_ohm"] == CONTROL_R_OHM else "")
                + f" | {codes} | {deltas} | {md} | {phase} | "
                f"{_ua(row['i_vrefp_a'])}{mark} | {_ua(row['i_vrefn_a'])}{mark} | "
                f"`{row['status']}`"
                + (f" {sorted(set(row['errors']))}" if row["errors"] else "")
                + " |"
            )
    lines += ["", *reference_current_lines(analysis, points, r_values)]
    lines += ["", *interpretation_lines(analysis, points, r_values)]
    lines += [
        "",
        "## What this testbench does not model",
        "",
        "- **Series resistance only.** Two resistors, one per reference pad, same value. "
        "No bond or trace inductance, no pad or bus capacitance, no decoupling network, "
        "no on-chip reference buffer.",
        "- **Nothing else on the net.** No other load, no other project's switching "
        "activity, no high-frequency behaviour of a shared bus.",
        "- **`VCM` and the supplies stay ideal at the die**, so the reference is the only "
        "non-ideal drive in the deck.",
        f"- **DC inputs.** {len(tb.measured_conversions())} DC differential levels, one "
        "conversion each, plus a discarded start-up conversion -- not a dynamic input.",
        f"- **One conversion rate.** `f_clk = {tb.F_CLK_HZ / 1e6:g}` MHz (DR-006 worst "
        f"case), `f_s = f_clk/{tb.PHASES_PER_CONVERSION} = "
        f"{tb.F_CLK_HZ / tb.PHASES_PER_CONVERSION / 1e6:g}` MS/s. A slower clock gives the "
        "reference longer to settle and would move these budgets up.",
        f"- **`R_ref = 0` is ngspice's zero-resistor floor** (1e-12 Ohm, rewritten with a "
        "warning), not a removed element.",
        "",
        "## Run",
        "",
        f"- ONE `klt sim` request, {len(points) * len(r_values)} units, status "
        f"`{info.get('status')}`, backend `{info.get('resolved_backend')}`, sharded "
        f"into {len(info.get('jobs') or [])} batch job(s) (`remote.hosts`).",
        f"- Executing PDK `{info.get('worker_pdk')}`, executing simulator "
        f"`{info.get('worker_ngspice')}` -- reported only because every shard agrees "
        f"(seen: {info.get('worker_pdks_seen')}, {info.get('worker_ngspice_seen')}).",
        f"- `corners.params` support on the worker image: "
        f"`{info.get('request_feature_status')}`. klt refuses rather than silently "
        "ignoring the axis, and this reader additionally refuses any corner that does "
        "not echo back its own `params`.",
        f"- request `corners/{prov.record_id}/request.json`, deck "
        f"`corners/{prov.record_id}/tb.spice`, report `corners/{prov.record_id}/report.json`",
        "",
        "| batch job | state | exit | instance | elapsed (s) | runner klt |",
        "|---|---|---|---|---|---|",
        *[
            f"| `{j['job_id']}` | `{j['state']}` | `{j['exit_code']}` | "
            f"`{j['instance_type']}` | {j['elapsed_seconds']} | `{j['runner_klt_version']}` |"
            for j in (info.get("jobs") or [])
        ],
        "",
        "**Uncontrolled difference.** The Environment block below names the PDK and ngspice "
        "resolved on the SUBMITTING host; the numbers above were produced by the executing "
        "worker named in this section. Where those differ, no comparison with a locally run "
        "record is controlled for PDK or simulator version.",
        "",
    ]
    klt_version = subprocess.run(
        ["klt", "--version"], capture_output=True, text=True, check=False).stdout.strip()
    worker_pdk = info.get("worker_pdk")
    worker_ng = info.get("worker_ngspice")
    pdk_line = (f"sky130A @ {worker_pdk.split()[-1]}" if worker_pdk else prov.pdk_line)
    ng_line = (worker_ng.split()[0] if worker_ng else prov.ng_version)
    lines += evidence.environment_block(
        pdk_line,
        ng_line,
        prov.netlist_sha,
        {
            "klt": klt_version,
            "solver options": fc.solver_settings_text(SOLVER_PROFILE),
            "tran card": f"`.tran {req['analysis']['args']}`",
            "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
            "DUT netlist sha256 above": "the assembled circuit body, not design/sar_adc_top.spice alone",
            "design/sar_adc_top.spice sha256": f"`{evidence.sha256_file(DUT_NETLIST)}`",
            "PDK / ngspice above": (
                "as reported by the executing worker" if worker_pdk and worker_ng
                else "submitting host (the worker reported none)"),
            "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",
        },
    )
    lines += [""]
    lines += evidence.footer_lines(RUNNER_REL, supersedes)
    evidence.write_latest_pointer(EXPERIMENT_DIR, prov.record_id)
    return evidence.close_record(prov, lines, "Record")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _r_list(text: str) -> list[float]:
    return [float(tok) for tok in text.replace(",", " ").split()]


def main(argv: list[str] | None = None) -> int:
    from harness import pdk

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check-env", action="store_true",
                    help="resolve the PDK and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the deck + request to --workdir and stop (no simulation)")
    ap.add_argument("--probe", action="store_true",
                    help="ONE unit (tt/27C/1.80V, R_ref = 0) through `klt sim --backend "
                         "local`, printing the captured codes -- the single-corner check "
                         "that the assembled deck reproduces the committed full-conversion "
                         "record before the grid is submitted")
    ap.add_argument("--record", action="store_true",
                    help="submit the full grid and mint an evidence record")
    ap.add_argument("--r-ohm", type=_r_list, default=list(DEFAULT_R_OHM),
                    help="comma/space separated R_ref sweep in Ohm (default: "
                         f"{','.join(_ohm(r) for r in DEFAULT_R_OHM)}); must contain "
                         f"{','.join(_ohm(r) for r in REQUIRED_R_OHM)}")
    ap.add_argument("--backend", default=None,
                    help="klt sim backend (default: klt's own / KLT_SIM_BACKEND). The "
                         "multi-corner grid goes to the batch fleet; it is never looped "
                         "locally.")
    ap.add_argument("--workdir", type=Path, default=None)
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S,
                    help="options.timeout_s, the per-UNIT limit (default: "
                         f"{DEFAULT_TIMEOUT_S:g})")
    ap.add_argument("--wait-for-capacity", type=float, default=DEFAULT_CAPACITY_WAIT_S,
                    help="seconds to wait for batch fleet capacity instead of failing the "
                         f"submit (default: {DEFAULT_CAPACITY_WAIT_S:g})")
    ap.add_argument("--hosts", type=int, default=None,
                    help="remote.hosts: how many batch jobs to shard the grid into "
                         "(default: the fewest whose shards fit the fleet's whole-job "
                         "ceiling even run serially -- see shard_count())")
    evidence.add_supersedes_argument(ap)
    args = ap.parse_args(argv)

    if args.check_env:
        info = pdk.resolve()
        print(f"PDK: {info.variant if info.found else info.error}")
        return 0 if info.found else 1

    r_values = check_r_values(args.r_ohm) if not args.probe else normalize_r_values(args.r_ohm)
    points = ratified_points()
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="sim-reference-drive-budget-"))
    fragment_text = tb.FRAGMENT_PATH.read_text()
    _body, meas_cards, tran_args = split_fragment(fragment_text)

    if args.dry_run:
        d = workdir / "grid"
        d.mkdir(parents=True, exist_ok=True)
        (d / "tb.spice").write_text(build_body(DUT_NETLIST.read_text(), fragment_text))
        req = build_request("tb.spice", points, r_values, meas_cards, tran_args,
                            timeout_s=args.timeout_s, backend=args.backend,
                            capacity_wait_s=args.wait_for_capacity,
                            hosts=args.hosts or shard_count(len(points) * len(r_values)))
        (d / "request.json").write_text(json.dumps(req, indent=1) + "\n")
        print(f"wrote deck + request for {len(points) * len(r_values)} units under {d}")
        return 0

    if args.probe:
        point = ("tt", 27.0, NOMINAL_SUPPLY_V)
        units, info, _req = submit(
            [point], [CONTROL_R_OHM], workdir,
            backend="local", timeout_s=args.timeout_s, capacity_wait_s=None,
            hosts=None, tag="probe")
        unit = units.get((point[0], point[1], point[2], CONTROL_R_OHM))
        if unit is None:
            print("probe: no unit in the report", file=sys.stderr)
            return 1
        row = decode_unit(unit)
        print(f"{corners_mod.corner_id(*point)} R_ref={_ohm(CONTROL_R_OHM)} Ohm: "
              f"status={row['status']} codes={row['codes']} "
              f"phase_ok={row['all_phase_ok']}")
        print(f"ideal codes: {ideal_codes()}")
        return 0 if row["complete"] else 1

    if args.record:
        units, info, req = submit(
            points, r_values, workdir, backend=args.backend, timeout_s=args.timeout_s,
            capacity_wait_s=args.wait_for_capacity,
            hosts=args.hosts or shard_count(len(points) * len(r_values)))
        result = analyze(units, points, r_values)
        for point in points:
            a = result[point]
            print(f"[{a['corner_id']}] "
                  + "  ".join(f"{t:g}LSB={_budget_cell(a['budgets'][t])}" for t in TIER_LSB),
                  flush=True)
        write_record(result, points, r_values, info, req, workdir, args.supersedes)
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

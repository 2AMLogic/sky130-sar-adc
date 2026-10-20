#!/usr/bin/env python3
"""Digital-partition characterization campaign (issue #619, T1 item 8
digital): maximum functioning clock bracket, rail power / energy per
conversion, and routed area, across the ratified nine-point OAT corner set.

    source sim/env.sh
    python3 sim/digital-partition/run_digital_partition.py --plan
    python3 sim/digital-partition/run_digital_partition.py --record

The partition is the walking-one ring sequencer + 10-bit register
(`design/sar_sequencer.sch`) PLUS the 33 top-level `sky130_fd_sc_hd` glue
instances `design/sar_adc_top.sch` adds directly (DR-008 readout recode and
CDAC drive, DR-009 balance/half-LSB enable) -- the exact partition
`signoff/block-manifest.json` calls digital. The netlist is taken verbatim
from the committed `design/sar_adc_top.spice`, so no schematic is re-netlisted
and the deck cannot drift from the design the rest of the repo verifies.

EVERY SIMULATION UNIT GOES THROUGH `klt sim` (this script never invokes
ngspice itself, and never loops it). The frequency search is adaptive per
corner but quantised to one shared grid, so each round submits ONE request per
distinct grid frequency covering every corner that wants it (at most nine
corners per job); the controller runs here, the simulations run on the
backend (default: `$KLT_SIM_BACKEND`, i.e. the Spot batch fleet on a dispatch
worker). A failed submit stops the campaign and is reported; it is never
retried on `local`. `--backend local` is accepted only with `--probe`, a
single-corner debug unit.

Declared limitations travel with every result (see digital_char.py's module
docstring and the record's Assumptions section): schematic-level only, no
extracted parasitics; loads and COMP_OUT arrival are experiment assumptions;
the bracket is a digital-partition bound, not the ADC sample rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM_DIR = HERE.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(HERE))

import digital_area  # noqa: E402
import digital_char as dc  # noqa: E402
import digital_report  # noqa: E402
from harness import corners as corners_mod, evidence, pdk  # noqa: E402

EXPERIMENT_DIR = HERE
REPO_ROOT = evidence.REPO_ROOT
TOP_NETLIST = REPO_ROOT / "design" / "sar_adc_top.spice"
CAMPAIGN_FILE = "campaign.json"


class SubmitError(RuntimeError):
    """A `klt sim` submission produced no usable report."""


def ratified_corner_ids() -> list[str]:
    return [cid for _p, _t, _v, cid in corners_mod.sweep(
        1.8, corners_mod.RATIFIED_SUPPLY_TOLERANCE, corners_mod.RATIFIED_PROCESS_CORNERS,
        corners_mod.RATIFIED_TEMPS_C, announce=False)]


def _default_runner(argv: list[str]) -> tuple[int, str, str]:
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.returncode, done.stdout, done.stderr


#: A shared fleet refuses a launch while it is at its concurrency cap
#: (`klt sim` does not wait this out itself in every client/runner pairing).
#: That refusal means "no capacity right now", not "the design failed", and
#: re-submitting to the SAME batch backend is the correct response. Any other
#: submit error stops the campaign.
CAPACITY_MARKERS = ("BATCH_MAX_CONCURRENT_INSTANCES", "batch_no_capacity", "no capacity")


def is_capacity_refusal(message: str) -> bool:
    return any(m.lower() in message.lower() for m in CAPACITY_MARKERS)


def make_submitter(workdir: Path, dut: dict, backend: str, runner=_default_runner,
                   timeout_s: float = 7200.0, batch: dict | None = None,
                   capacity_retries: int = 40, retry_wait_s: float = 120.0, sleep=None):
    """`submit(f_mhz, corner_ids)` -> (UnitResults, run info). Reports are
    cached in `workdir` keyed by (frequency, corner set), so a campaign that
    died partway resumes without re-spending completed fleet jobs."""

    def submit(f_mhz: float, cids):
        key = hashlib.sha1(",".join(sorted(cids)).encode()).hexdigest()[:8]
        d = workdir / f"f{f_mhz:09.4f}MHz_{key}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "tb.spice").write_text(dc.build_netlist(f_mhz, dut))
        req = dc.build_request("tb.spice", f_mhz, cids, timeout_s=timeout_s, backend=backend, batch=batch)
        (d / "request.json").write_text(dc.dumps(req))
        rep_path = d / "report.json"
        if rep_path.is_file():
            report = json.loads(rep_path.read_text())
        else:
            argv = ["klt", "sim", str(d / "request.json"), "--backend", backend,
                    "--format", "json", "-o", str(d / "out")]
            import time
            nap = sleep or time.sleep
            for attempt in range(capacity_retries + 1):
                rc, out, err = runner(argv)
                try:
                    try:
                        report = json.loads(out)
                    except json.JSONDecodeError:
                        report = json.loads(err)  # `klt` writes its error envelope to stderr (rc 1)
                except json.JSONDecodeError as exc:
                    raise SubmitError(
                        f"klt sim ({backend}) at {f_mhz:.3f} MHz returned no JSON report "
                        f"(rc={rc}): {(err or out)[:600]}") from exc
                if "error" in report and "corners" not in report:
                    msg = json.dumps(report["error"])
                    if is_capacity_refusal(msg) and attempt < capacity_retries:
                        print(f"fleet at capacity; retrying {f_mhz:.3f} MHz in {retry_wait_s:.0f}s "
                              f"({attempt + 1}/{capacity_retries})", file=sys.stderr, flush=True)
                        nap(retry_wait_s)
                        continue
                    raise SubmitError(f"klt sim ({backend}) at {f_mhz:.3f} MHz: {msg}")
                break
            rep_path.write_text(json.dumps(report, indent=1) + "\n")
        results, info = dc.read_report(report)
        info = dict(info, backend=backend, request=str(d.name))
        return results, info

    return submit


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------

def _fmt_f(v):
    return "n/a" if v is None else f"{v:.2f}"


def render_record(rec_id: str, camp: dict, supersedes: str, written_by: str) -> list[str]:
    s = camp["summary"]
    L: list[str] = []
    a = L.append
    a(f"# Digital-partition characterization (Fmax bracket, rail power, area) -- {rec_id}")
    a("")
    a(f"- **Record ID**: {rec_id}")
    a("- **Claim**: characterizes the declared digital partition (`design/sar_sequencer.sch` "
      "sequencer + the 33 top-level `sky130_fd_sc_hd` glue instances of `design/sar_adc_top.sch`) "
      "at the ratified nine-point OAT corner set: (1) a measured clock-frequency bracket "
      "(highest tested passing / next failing, or a censored lower bound) under functional "
      "checks over four back-to-back conversions; (2) digital-rail average power, idle/reset "
      "power and energy per conversion at the provisional 12 MHz operating point; (3) routed "
      "area from the committed routed artifacts. Schematic-level, digital-partition-only; "
      "NOT extracted timing, NOT static timing analysis, and NOT the ADC sample rate. No claim "
      "is graded against a ratified spec row (`spec/target-spec.md` is entirely DRAFT).")
    n_ok = sum(1 for r in s["results"].values() if r["state"] in (dc.STATE_BRACKET, dc.STATE_CENSORED))
    a(f"- **Corner matrix run**: process={corners_mod.RATIFIED_PROCESS_CORNERS}, "
      f"temperature_c={corners_mod.RATIFIED_TEMPS_C}, supply_v=[1.62, 1.8, 1.98] "
      f"({len(s['results'])} points, one-at-a-time per sim/README.md)")
    a(f"- **Overall**: {n_ok}/{len(s['results'])} corners yield a bracket or declared lower bound; "
      f"negative control (too-fast {dc.NEGATIVE_CONTROL_MHZ:g} MHz clock) "
      f"{'FAILS at every corner as required' if s['negative_control']['ok'] else 'DID NOT fail everywhere -- checker not trusted'}; "
      f"item-8 digital checklist: {'MET' if s['checklist']['meets'] else 'NOT MET'}.")
    a(f"- **Measured value(s)**: see the per-corner tables below (frequency bracket, power, energy "
      f"per conversion) and the area section; raw data in `runs/{rec_id}/{CAMPAIGN_FILE}`.")
    a("")
    a("## Search declaration")
    a("")
    a(f"- Grid: f = {dc.F_BASE_MHZ:g} MHz x 2^(i/{dc.STEPS_PER_OCTAVE}); adjacent points differ by "
      f"{dc.tolerance_pct():.2f} % (the declared search tolerance).")
    a(f"- Coarse ladder: one octave per rung from {dc.F_BASE_MHZ:g} MHz; ceiling "
      f"{dc.freq_mhz(dc.CEILING_INDEX):g} MHz (index {dc.CEILING_INDEX}). A corner still passing at "
      "the ceiling is reported as a LOWER BOUND (censored), not an Fmax.")
    a("- Then bisection on grid indices between the highest coarse pass and the first coarse fail, "
      "until adjacent grid points bracket the transition. Monotonicity is assumed and CHECKED: any "
      "pass above the lowest fail flags the corner non-monotone.")
    a("- A probe is INVALID (never a pass, never a fail) if any check value is missing or "
      "non-finite, or the simulator reports an error for the corner; an invalid probe freezes that "
      "corner's search as `inconclusive`.")
    a(f"- Checks per probe: {len(dc.expected_checks())} `.meas` values over {len(dc.CODES)} "
      f"conversions: one-hot phase order after every clock edge, reset state, restart (ph_sample "
      f"re-entry), BUSY / HALF_LSB_EN / HALF_LSB_ENN control outputs after every edge, and at "
      f"end-of-conversion the captured code, ADCOUT recode and SELn/SELp. Sampled "
      f"{dc.SAMPLE_T} T after each launching edge.")
    a("")
    a("## Frequency bracket per corner")
    a("")
    a("| Corner | State | Highest passing (MHz) | Next failing (MHz) | Non-monotone | Probes |")
    a("|---|---|---:|---:|---|---:|")
    for cid, r in s["results"].items():
        a(f"| `{cid}` | {r['state']} | {_fmt_f(r['f_pass_mhz'])} | {_fmt_f(r['f_fail_mhz'])} | "
          f"{'YES' if r['non_monotone'] else 'no'} | {r['n_probes']} |")
    a("")
    a("A `censored_lower_bound` row means the corner never failed up to the declared ceiling: its "
      "highest passing frequency is a lower bound on the true limit, not the limit. "
      "`nonfunctional_at_floor` means the partition already fails at the 12 MHz operating point.")
    a("")
    a("## Rail power and energy per conversion (12 MHz operating point)")
    a("")
    a("| Corner | Functional @12 MHz | P_active (uW) | P_idle/reset (uW) | E/conversion (pJ) |")
    a("|---|---|---:|---:|---:|")
    for cid, p in s["power"].items():
        pa = "invalid" if p["p_active_w"] is None else f"{p['p_active_w'] * 1e6:.3f}"
        pr = "invalid" if p["p_reset_w"] is None else f"{p['p_reset_w'] * 1e6:.3f}"
        en = "invalid" if p["energy_per_conversion_j"] is None else f"{p['energy_per_conversion_j'] * 1e12:.3f}"
        fo = {True: "yes", False: "NO (nonfunctional)", None: "unknown"}[p["functional_at_op"]]
        a(f"| `{cid}` | {fo} | {pa} | {pr} | {en} |")
    a("")
    a("- **Supply polarity**: the DUT is powered from the positive digital rail `VPWR` against `VGND` "
      "= 0 V (DR-010 digital domain); the rail source is `Vdig`, and a sourcing supply reads "
      "NEGATIVE `i(Vdig)`, so P = -avg(i(Vdig)) x V.")
    c0, c1 = dc.POWER_WINDOW_CONVERSIONS
    a(f"- **Active window**: whole conversions {c0}..{c1 - 1} ({c1 - c0} conversions, edge to edge, "
      f"codes {', '.join(str(x) for x in dc.CODES[c0:c1])} -- conversion 0 is excluded because its data registers start "
      "from reset). **Idle/reset window**: RST_B asserted with the clock running, two whole periods "
      "(edges 2..4). Clock-stopped static leakage is NOT separately measured.")
    a("- **Switching pattern**: free-running 50 % duty clock at 12 MHz; COMP_OUT driven per the "
      f"deterministic code sequence {dc.CODES} so the data registers toggle (all-ones / all-zeros codes are not exercised); "
      f"COMP_OUT changes {dc.COMP_DELAY_T} T after each launching edge.")
    a("- **Interface loads (assumptions, not spec values)**: " +
      ", ".join(f"{k} {v * 1e15:g} fF" for k, v in dc.LOADS_F.items()) +
      ". The energy delivered into these loads is INSIDE the measurement (drawn through `Vdig`).")
    a("- **Outside the DUT boundary**: the CLK, RST_B and COMP_OUT input drivers (ideal behavioural "
      "sources) and the monitor nodes (high impedance); their energy is not in any power figure.")
    a("")
    a("## Area (geometry-derived; independent of electrical corner)")
    a("")
    ar = s["area"]
    if ar:
        a(f"- **Composed footprint**: {ar['composed_footprint_um2']:.1f} um^2 -- bounding box of the two routed "
          f"macros as placed in the composed top (includes the gap between them).")
        a(f"- **Macro area (sum, macros proven disjoint)**: {ar['macro_area_um2']:.1f} um^2 -- DEF DIEAREA of "
          "`sar_sequencer` + `top_glue` (includes the placer's core margin and unused sites).")
        if "placed_cell_area_um2" in ar:
            a(f"- **Placed-cell area**: {ar['placed_cell_area_um2']:.1f} um^2 (logic cells "
              f"{ar['logic_cell_area_um2']:.1f} um^2; remainder is fill/tap) -- LEF footprints of every routed component.")
        for m, info in ar["macros"].items():
            a(f"  - `{m}`: die {info['die_um'][0]:.3f} x {info['die_um'][1]:.3f} um, "
              f"{info['component_count']} routed components, origin {info['origin_um']}")
        for n in ar["metric_notes"]:
            a(f"- {n}")
    else:
        a("- area derivation not available")
    a("")
    a("## Negative control")
    a("")
    nc = s["negative_control"]
    a(f"A {nc['f_mhz']:g} MHz clock (far beyond what the partition can follow) was run at every "
      "corner through the same checks. It must be graded FAIL everywhere; a pass would mean the "
      "checks cannot detect failure.")
    a("")
    a("| Corner | Graded |")
    a("|---|---|")
    for cid, g in nc["per_corner"].items():
        a(f"| `{cid}` | {'FAIL (as required)' if g['passed'] is False else ('PASS (CHECKER BROKEN)' if g['passed'] else 'INVALID')} |")
    a("")
    a("## Assumptions and limitations")
    a("")
    a("- Schematic-level transistor SPICE of `design/sar_adc_top.spice` cells: no extracted "
      "parasitics, no routing RC. Post-layout verification of the digital partition remains a "
      "separate requirement; this record does not claim extracted timing.")
    a("- The bracket is a functional limit of the digital partition alone under the stated loads "
      "and COMP_OUT arrival (ideal source, 0.25 T after the launching edge: the comparator "
      "decision time is not included). It is NOT the reciprocal of any one propagation delay, "
      "and digital Fmax does not set the ADC sample rate (which also depends on the sampling "
      "front end, the CDAC and the comparator).")
    a(f"- Input edges (CLK, RST_B, COMP_OUT): 5 % of the period, clamped to [{dc.RISE_MIN_S * 1e12:g} ps, "
      f"{dc.RISE_MAX_S * 1e9:g} ns]; solver max step = edge time / {dc.STEP_DIVISOR:g}. Slower (1-2 ns) edges were found "
      "to corrupt cold-corner register captures in this deck and are not used; RST_B is released 0.3 T "
      "before the first advancing clock edge (clock-low phase).")
    a("- Checks sample at 0.9 T after each launching edge, so 'passing' means settled one tenth of "
      "a period before the next edge.")
    a("- No mid-conversion asynchronous reset is injected: reset coverage is the power-up reset "
      "state, release, and the automatic restart after each conversion.")
    a("- The 12 MHz point is the existing PROVISIONAL operating point (DR-006-derived), not a "
      "ratified spec value; the sample-rate target remains DRAFT.")
    a("")
    a("## Provenance")
    a("")
    for k, v in camp["pins"].items():
        a(f"- {k}: `{v}`" if not isinstance(v, (dict, list)) else f"- {k}: `{json.dumps(v, sort_keys=True)}`")
    a("")
    skew = dc.runner_skew(camp["probe_log"], [camp.get("negative_control_run") or {}])
    if skew:
        a("### Runner / client version skew (disclosed)")
        a("")
        for m in skew:
            a(f"- {m}; the campaign ran with `batch.runner_version_check: warn` "
              "(`--allow-runner-skew`) because the fleet image lags the client. The request uses only "
              "features present in both (circuit-body netlist, `.meas` cards, supply `alter`, `exclude`); "
              "every probe is graded by this repository's own checks rather than by the runner's status "
              "(the per-probe `report.json` measurements under `corners/<record>/`), and the negative "
              "control fails at every corner under the same runner. No same-version re-run is part of "
              "this record: the results stand on the committed fleet reports alone.")
        a("")
    a("### Submissions")
    a("")
    for e in camp["probe_log"]:
        run = e["run"]
        a(f"- idx {e['index']} ({e['f_mhz']:.3f} MHz), {len(e['corners'])} corner(s): backend "
          f"`{run.get('backend')}`, remote `{json.dumps(run.get('remote'), sort_keys=True)}`, "
          f"status `{run.get('status')}`")
    nc_run = camp.get("negative_control_run")
    if nc_run:
        a(f"- negative control ({nc['f_mhz']:g} MHz), all corners: backend `{nc_run.get('backend')}`, "
          f"remote `{json.dumps(nc_run.get('remote'), sort_keys=True)}`, status `{nc_run.get('status')}`")
    a("")
    if not s["checklist"]["meets"]:
        a("## Unmet checklist items")
        a("")
        for r in s["checklist"]["reasons"]:
            a(f"- {r}")
        a("")
    env = dict(camp["environment"])
    ng = env.pop("ngspice line")
    sha = env.pop("12 MHz tt deck netlist sha256")
    L.extend(evidence.environment_block(camp["pins"]["PDK"], ng, sha, extra=env))
    a("")
    L.extend(evidence.footer_lines(written_by, supersedes))
    return L


def pins(dut_text_sha: str, pdk_line: str) -> dict:
    return {
        "digital partition netlist sha256": digital_report.partition_netlist_sha(TOP_NETLIST.read_text()),
        "design/sar_adc_top.spice sha256 (informational; whole file incl. analog)": digital_area.sha256_file(TOP_NETLIST),
        "design/sar_sequencer.sch sha256": digital_area.sha256_file(REPO_ROOT / "design/sar_sequencer.sch"),
        "design/sar_adc_top.sch sha256": digital_area.sha256_file(REPO_ROOT / "design/sar_adc_top.sch"),
        "digital deck generator sha256 (informational)": digital_area.sha256_file(HERE / "digital_char.py"),
        "PDK": pdk_line,
        "frequency grid": f"{dc.F_BASE_MHZ:g} MHz x 2^(i/{dc.STEPS_PER_OCTAVE}), ceiling index {dc.CEILING_INDEX}",
    }


def mint_record(camp: dict, supersedes: str, probe_dir: Path) -> Path:
    deck_12 = (probe_dir / next(p.name for p in sorted(probe_dir.iterdir())
                                if p.name.startswith("f0012.0000MHz")) / "tb.spice").read_text()
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, deck_12)
    rid = prov.record_id
    camp["record_id"] = rid
    camp["environment"].update({
        "local ngspice (informational; simulations ran on the backend)": prov.ng_version,
        "12 MHz tt deck netlist sha256": prov.netlist_sha,
    })
    engines = set()
    for rp in probe_dir.glob("*/report.json"):
        try:
            env = json.loads(rp.read_text()).get("environment") or {}
        except json.JSONDecodeError:
            continue
        engines.add(f"{env.get('engine')} {env.get('engine_version')}")
    camp["environment"]["engine (from reports)"] = ", ".join(sorted(engines))
    vers = sorted({str(json.loads(rp.read_text()).get("environment", {}).get("engine_version"))
                   for rp in probe_dir.glob("*/report.json")})
    camp["environment"]["ngspice line"] = ", ".join(f"ngspice-{v}" for v in vers) if vers else "unknown"
    camp["pins"]["netlist-snapshot sha256"] = "sha256:" + prov.netlist_sha
    # raw artifacts (append-only dirs)
    cdir = EXPERIMENT_DIR / "corners" / rid
    cdir.mkdir(parents=True, exist_ok=True)
    for d in sorted(probe_dir.iterdir()):
        if not d.is_dir():
            continue
        dest = cdir / d.name
        dest.mkdir(exist_ok=True)
        for fn in ("tb.spice", "request.json", "report.json"):
            if (d / fn).is_file():
                shutil.copy2(d / fn, dest / fn)
        for log in sorted((d / "out").glob("*/ngspice.log")) if (d / "out").is_dir() else []:
            shutil.copy2(log, dest / f"{log.parent.name}.ngspice.log")
    rdir = EXPERIMENT_DIR / "runs" / rid
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / CAMPAIGN_FILE).write_text(dc.dumps(camp))
    lines = render_record(rid, camp, supersedes, "sim/digital-partition/run_digital_partition.py")
    prov.record_path.write_text("\n".join(lines) + "\n")
    evidence.write_latest_pointer(EXPERIMENT_DIR, rid)
    print(f"Record written: {prov.record_path.relative_to(REPO_ROOT)}")
    return prov.record_path


def run_campaign(backend: str, probe_dir: Path, max_workers: int, runner=_default_runner,
                 batch: dict | None = None) -> dict:
    dut = dc.extract_dut(TOP_NETLIST.read_text())
    if len(dut["glue"]) != dc.GLUE_EXPECTED_INSTANCES:
        raise SystemExit(f"expected {dc.GLUE_EXPECTED_INSTANCES} glue instances, found {len(dut['glue'])}")
    cids = ratified_corner_ids()
    import threading
    raw_submit = make_submitter(probe_dir, dut, backend, runner, batch=batch)
    gate = threading.BoundedSemaphore(max_workers)  # host cap on concurrent submits, search + control combined

    def submit(f_mhz, cs):
        with gate:
            return raw_submit(f_mhz, cs)

    # The too-fast negative control does not depend on the search, so it
    # runs concurrently with it (one extra fleet job, no extra round).
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        nc_future = pool.submit(submit, dc.NEGATIVE_CONTROL_MHZ, cids)
        searches, log, units = dc.run_search(cids, submit, max_workers=max_workers)
        nc_results, nc_info = nc_future.result()
    neg = {c: dc.grade_unit(nc_results.get(c)) for c in cids}
    area = digital_area.derive(
        REPO_ROOT, lef_path=pdk.resolve().variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "lef" / "sky130_fd_sc_hd.lef")
    summary = dc.summarize(searches, units, neg, area)
    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    engines = sorted({str(e["run"].get("remote")) for e in log})
    return {
        "summary": summary,
        "probe_log": log,
        "negative_control_run": nc_info,
        "pins": pins("", pdk_line),
        "environment": {"backend": backend, "klt": _klt_version(), "remote jobs": ", ".join(engines),
                        "batch options": json.dumps(batch or {}, sort_keys=True)},
    }


def _klt_version() -> str:
    try:
        return subprocess.run(["klt", "--version"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true", help="print the corner list, grid and checks; submit nothing")
    ap.add_argument("--record", action="store_true", help="mint an append-only evidence record")
    ap.add_argument("--backend", default=os.environ.get("KLT_SIM_BACKEND", "batch"))
    ap.add_argument("--workdir", type=Path, default=None,
                    help="probe cache/scratch (resume a partly completed campaign)")
    ap.add_argument("--max-workers", type=int, default=2, help="concurrent submits (host cap: 2)")
    ap.add_argument("--capacity-wait-s", type=float, default=3600.0,
                    help="batch.capacity_wait_s: wait this long out a fleet capacity refusal")
    ap.add_argument("--allow-runner-skew", action="store_true",
                    help="batch.runner_version_check=warn: run on a fleet runner whose klt version "
                         "differs from the client's (disclosed in the record). Default: enforce.")
    ap.add_argument("--probe", nargs=2, metavar=("CORNER_ID", "MHZ"),
                    help="ONE single-corner debug unit (may use --backend local)")
    evidence.add_supersedes_argument(ap)
    args = ap.parse_args()

    if args.plan:
        print("corners:", *ratified_corner_ids())
        print(f"grid: {dc.F_BASE_MHZ:g} MHz x 2^(i/{dc.STEPS_PER_OCTAVE}), ceiling {dc.freq_mhz(dc.CEILING_INDEX):g} MHz, "
              f"tolerance {dc.tolerance_pct():.2f} %, negative control {dc.NEGATIVE_CONTROL_MHZ:g} MHz")
        print(f"checks per probe: {len(dc.expected_checks())}")
        return 0

    if args.max_workers > 2:
        print("--max-workers above 2 is not allowed on a shared dispatch host", file=sys.stderr)
        return 2
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="digital-partition-"))
    workdir.mkdir(parents=True, exist_ok=True)

    batch = {"capacity_wait_s": args.capacity_wait_s}
    if args.allow_runner_skew:
        batch["runner_version_check"] = "warn"

    if args.probe:
        cid, mhz = args.probe
        dut = dc.extract_dut(TOP_NETLIST.read_text())
        results, info = make_submitter(workdir, dut, args.backend, batch=batch)(float(mhz), [cid])
        g = dc.grade_unit(results.get(cid))
        print(json.dumps({"corner": cid, "f_mhz": float(mhz), "passed": g.passed,
                          "failures": g.failures[:10], "invalid": g.invalid[:5], "run": info}, indent=1))
        return 0 if g.passed else 1

    if args.backend == "local":
        print("refusing to run the corner campaign on `local`: a dispatch worker submits grids to the "
              "batch fleet (use --probe for a single debug unit)", file=sys.stderr)
        return 2
    try:
        camp = run_campaign(args.backend, workdir, args.max_workers, batch=batch)
    except (SubmitError, dc.InfrastructureError, ValueError) as exc:
        print(f"CAMPAIGN STOPPED: {exc}", file=sys.stderr)
        print(f"completed probes are cached in {workdir}; no evidence minted", file=sys.stderr)
        return 3
    s = camp["summary"]
    for cid, r in s["results"].items():
        print(f"{cid}: {r['state']} pass={_fmt_f(r['f_pass_mhz'])} fail={_fmt_f(r['f_fail_mhz'])}")
    print("negative control ok:", s["negative_control"]["ok"])
    print("checklist:", "MET" if s["checklist"]["meets"] else "NOT MET", s["checklist"]["reasons"])
    if args.record:
        mint_record(camp, args.supersedes, workdir)
    return 0 if s["checklist"]["meets"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

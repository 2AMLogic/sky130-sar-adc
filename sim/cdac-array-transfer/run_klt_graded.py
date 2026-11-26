#!/usr/bin/env python3
"""Graded `klt sim` campaign for the three ratified CDAC rows (issue #1021).

`testbench/klt/request.json` (issue #564's pilot) measures ten top-plate
voltages per corner with NO limits and NO spec_row tag, so it grades no spec
row: three RATIFIED rows (`V_REF`, LSB, Sampling cap) cite it only through
`run_transfer.py --ratified-record`'s structural + functional/monotonicity
record, whose own Claim says no numeric error-tolerance is ratified. This
runner drives the SIBLING request `testbench/klt/request-graded.json` --
same DUT, same 9-point ratified OAT corner grid -- which adds the row
observables and machine-evaluates what can be machine-evaluated without
inventing a tolerance (CLAUDE.md: agents do not choose spec tolerances):

  V_REF        GRADED in-envelope. `vref_ratio` (limits 1 +/- 1e-5 relative)
               and `v_vrefn` (limits +/- 1e-5 V) carry `spec_row: v_ref`:
               the applied reference at the CDAC equals the corner's own
               rail per the ratified relation `V_REF = V_DD` (DR-003). The
               slack is solver/print precision only, not a design
               tolerance: 1e-5 relative is twice the 6-significant-digit
               `.meas` print half-step just above unity (5e-6) and >= 16x ngspice's
               default `vntol` = 1e-6 V referred to the 1.62 V rail corner.
  LSB          NOT graded in-envelope. The per-corner differential step is
               measured (mono steps + vdiff values) but the ratified row
               gives no tolerance on its deviation from
               `2*V_REF/2^N = 3.5156 mV`, so no pass condition is written;
               the step deviation is reported informationally and the gap
               decision is owned by
               spec/decision-records/DR-026-cdac-row-tolerance-decisions.md
               (proposed). Monotonicity/polarity carry limits but NO
               spec_row tag on purpose: a passing monotonicity check must
               not be readable by the signoff grader as the LSB row being
               covered (that is exactly the "widen the envelope to cover
               the row" move issue #1021 rejects).
  Sampling cap NOT graded in-envelope. The exact structural values (plate
               side 1.9000 um, 512 positions/side) are re-checked by this
               runner via run_transfer.check_structural_sizing(); the
               ELECTRICAL unit cap is observed informationally as
               cu_elec = |q_vrefp| / (vdd * S), where q_vrefp integrates
               the reference charge drawn during redistribution and S is
               the exact charge-equivalent switched-unit count derived in
               SWITCHED_UNITS_EQ below. Its deviation from the ratified
               "C_u ~= 8.66 fF" has no ratified tolerance either, so it
               grades nothing and feeds the same decision record.

Usage:
    python3 sim/cdac-array-transfer/run_klt_graded.py --record

The submit goes through `klt sim` (batch fleet on a dispatch host via
$KLT_SIM_BACKEND), always with `--wait-for-capacity 600` (the shared
harness's fleet-capacity policy, sim/harness/klt_sim.py). The report is
cached beside the record, so a re-run after a crash resumes without
re-spending fleet jobs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
sys.path.insert(0, str(SIM_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import corners as corners_mod  # noqa: E402
from harness import evidence, klt_sim  # noqa: E402
import run_transfer  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
REQUEST = EXPERIMENT_DIR / "testbench" / "klt" / "request-graded.json"
TB_BODY = EXPERIMENT_DIR / "testbench" / "klt" / "tb_body.spice"
FRAGMENT = run_transfer.FRAGMENT
CODES = run_transfer.CODES
VREF_BOUNDS = {
    "vref_ratio": ("ratio", {"min": 0.99999, "max": 1.00001}),
    "v_vrefn": ("V", {"min": -1e-5, "max": 1e-5}),
}

#: Charge-equivalent switched-unit count for `q_vrefp`. For one array side
#: whose `sw` of 512 unit positions step their bottom plates from VREFN to
#: VREFP, charge conservation on the (floating) top plate gives
#: dv_top = sw*vdd/512, so the charge drawn from VREFP is
#: C_u * (sw*vdd - sw*dv_top) = C_u*vdd*sw*(1 - sw/512) per side -- NOT
#: C_u*vdd*sw: the top-plate redistribution returns most of it. (In the
#: netlist each top plate is reset to Vcm = vdd/2, not 0, with every bottom
#: plate at VREFN; the Vcm terms cancel -- per switched unit the charge from
#: VREFP is C_u*(vdd - v_top_final) - C_u*(0 - Vcm) = C_u*vdd*(1 - sw/512)
#: -- so the shorthand above reaches the same result.) Each
#: measured code drives the P side with `code` and the N side with
#: `511 - code` switched units; the five codes are parallel array copies
#: sharing one reset event, so the whole-transient integral is a sum of five
#: independent single-switch events and the five-code set's exact equivalent
#: is the sum below (328699/512 = 641.990234375 unit positions). This is an
#: analytic derivation only: no calibration deck or run checks it, and none
#: is committed.
SWITCHED_UNITS_EQ = sum(
    sw * (1 - sw / 512.0) + (511 - sw) * (1 - (511 - sw) / 512.0)
    for sw in CODES
)

BASELINE_RECORD = "20261001-120402-d24f700"


def _baseline_pdk_commit(record_id: str) -> str:
    """PDK commit stamped in the baseline record's own `- PDK:` line."""
    text = (EXPERIMENT_DIR / "records" / f"{record_id}.md").read_text()
    m = re.search(r"^- PDK: \S+ @ ([0-9a-f]{40})\s*$", text, re.M)
    return m.group(1) if m else "unknown"


def _baseline_cid(corner: dict) -> str:
    vdd = (corner.get("params") or {}).get("vdd_val")
    return corners_mod.corner_id(
        corner["process"], float(corner["temperature_c"]), float(vdd)
    )


def _vref_measurements(container: dict, source: str):
    if not isinstance(container, dict) or not isinstance(container.get("measurements"), list):
        raise ValueError(f"{source} requires a measurements list")
    measurements = container["measurements"]
    for name, (unit, limits) in VREF_BOUNDS.items():
        matches = [m for m in measurements if isinstance(m, dict) and m.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"{source} must contain exactly one {name} measurement")
        if matches[0].get("unit") != unit:
            raise ValueError(f"{source} {name} must use unit {unit}")
        yield name, limits, matches[0]


def _check_vref_definitions(container: dict, source: str) -> None:
    for name, limits, measurement in _vref_measurements(container, source):
        if measurement.get("spec_row") != "v_ref" or measurement.get("limits") != limits:
            raise ValueError(f"{source} {name} must grade spec_row v_ref with limits {limits}")


def _graded_request_sha256() -> str:
    text = REQUEST.read_text()
    _check_vref_definitions(json.loads(text), "request")
    return evidence.sha256_text(text)


def _check_vref_results(corner: dict) -> None:
    source = f"corner {corner.get('corner_id')}"
    for name, limits, result in _vref_measurements(corner, source):
        value = result.get("value")
        if not klt_sim.finite(value) or not result.get("status"):
            raise ValueError(f"{source} {name} requires a finite value and measurement status")
        if result["status"] == "pass":
            if not limits["min"] <= value <= limits["max"]:
                raise ValueError(f"{source} {name} reports pass with value {value} outside {limits}")
            margin = result.get("margin")
            if not klt_sim.finite(margin) or margin < 0:
                raise ValueError(f"{source} {name} reports pass without a finite nonnegative margin")


def run(backend: str | None, request: Path, record_id: str, stderr_path: Path):
    """Submit the request and return (report, run_facts)."""
    outdir = EXPERIMENT_DIR / "klt-sim" / record_id / "out"
    report_path = EXPERIMENT_DIR / "klt-sim" / record_id / "report.json"

    def tee_runner(argv):
        rc, out, err = klt_sim.default_runner(argv)
        stderr_path.write_text(err)
        return rc, out, err

    report = klt_sim.submit(
        request, outdir, backend=backend, report_path=report_path,
        label="cdac-graded", runner=tee_runner,
    )
    return report, klt_sim.run_info(report)


def write_record(
    report: dict,
    info: dict,
    record_id: str,
    *,
    request_sha256: str,
    raw_run_id: str,
    note: str = "",
    supersedes: str = "",
) -> tuple[Path, bool, str]:
    corners = report.get("corners", [])

    # Check the submission, full-grid census and worker pins before writing evidence.
    pdk_raw = json.loads((SIM_DIR / "pdk.json").read_text())
    tc_raw = json.loads((SIM_DIR / "toolchain.json").read_text())
    worker_pdk = info.get("worker_pdk")
    worker_ng = info.get("worker_ngspice")
    problems: list[str] = []
    try:
        if request_sha256 != _graded_request_sha256():
            problems.append("graded request differs from the submission")
        _check_vref_definitions(report, "report")
        for corner in corners:
            _check_vref_results(corner)
    except ValueError as exc:
        problems.append(str(exc))
    expected = corners_mod.ratified_oat_grid(
        run_transfer.NOMINAL_SUPPLY_V, run_transfer.SUPPLY_TOLERANCE,
        run_transfer.PROCESS_CORNERS, run_transfer.TEMPS_C,
    )
    observed = [
        (c.get("process"), c.get("temperature_c"), (c.get("params") or {}).get("vdd_val"))
        for c in corners
    ]
    if len(observed) != len(expected) or set(observed) != set(expected):
        problems.append("report must contain each ratified process/temperature/supply point exactly once")
    passed = sum(c.get("status") == "pass" for c in corners)
    if report.get("corner_count") != len(corners) or report.get("passed") != passed:
        problems.append("reported corner counts disagree with per-corner statuses")

    if not worker_pdk:
        problems.append("worker PDK stamp not reported (or shards disagree)")
    else:
        variant, _, commit = worker_pdk.partition(" @ ")
        if variant != pdk_raw.get("variant") or commit.lower() != str(
            pdk_raw.get("open_pdks_commit", "")
        ).lower():
            problems.append(
                f"worker PDK stamp {worker_pdk!r} != sim/pdk.json pin "
                f"({pdk_raw.get('variant')} @ {pdk_raw.get('open_pdks_commit')})"
            )
    if not worker_ng:
        problems.append("worker ngspice banner not reported (or shards disagree)")
    else:
        major = int(worker_ng.split("-")[-1])
        if major < int(tc_raw["ngspice_min_major"]):
            problems.append(
                f"worker {worker_ng} below sim/toolchain.json floor "
                f"{tc_raw['ngspice_min_major']}"
            )
    if problems:
        return (EXPERIMENT_DIR / "records" / f"{record_id}.md"), False, "; ".join(problems)

    # ---- structural census (the sampling-cap row's exact, corner-invariant part)
    struct_ok, struct_problems = run_transfer.check_structural_sizing()

    # ---- per-corner decoding
    rows = []
    for corner in corners:
        cid = _baseline_cid(corner)
        m = {mm["name"]: mm for mm in corner.get("measurements", [])}
        vdd = float((corner.get("params") or {}).get("vdd_val"))
        per_code = {}
        for code in CODES:
            vp, vn = m[f"vtop_p_{code}"]["value"], m[f"vtop_n_{code}"]["value"]
            vdiff = vp - vn
            ideal = run_transfer.ideal_vdiff(code, vdd)
            per_code[code] = dict(
                vtop_p=vp, vtop_n=vn, vdiff=vdiff,
                ideal=ideal,
                err_mv=(vdiff - ideal) * 1000.0,
            )
        vals = [per_code[c]["vdiff"] for c in CODES]
        gaps = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
        rows.append(dict(
            corner_id=cid, cid_klt=corner["corner_id"], vdd=vdd, m=m, per_code=per_code,
            monotonic=all(g > 0 for g in gaps),
            correct_sign=vals[0] < 0 < vals[-1],
            min_gap=min(gaps),
            vref_ratio=m["vref_ratio"]["value"],
            vref_ratio_status=m["vref_ratio"]["status"],
            v_vrefn=m["v_vrefn"]["value"],
            v_vrefn_status=m["v_vrefn"]["status"],
            lsb_derived_mv=2 * (m["v_vrefp"]["value"] - m["v_vrefn"]["value"]) / 1024 * 1000.0,
            step_dev_pct=max(
                abs((per_code[c2]["vdiff"] - per_code[c1]["vdiff"])
                    / (per_code[c2]["ideal"] - per_code[c1]["ideal"]) - 1.0) * 100.0
                for c1, c2 in zip(CODES, CODES[1:])
            ),
            cu_elec_ff=abs(m["q_vrefp"]["value"]) / (vdd * SWITCHED_UNITS_EQ) * 1e15,
        ))

    graded_ok = all(
        m.get("status") == "pass" for _, _, m in _vref_measurements(report, "report")
    ) and all(
        r["vref_ratio_status"] == "pass" and r["v_vrefn_status"] == "pass" for r in rows
    )
    functional_ok = all(r["monotonic"] and r["correct_sign"] for r in rows)
    report_pass = report.get("status") == "pass" and passed == len(corners)
    overall_ok = report_pass and graded_ok and functional_ok and struct_ok
    binding = max(rows, key=lambda r: abs(r["vref_ratio"] - 1.0))

    # ---- baseline-agreement probe (issue #564's comparator; #811's gate, informational here)
    from compare_klt_envelope import load_baseline, compare

    cmp_res = compare(report, load_baseline(BASELINE_RECORD))

    # ---- derived-quantity bookkeeping for the record text
    max_err_mv = max(abs(r["per_code"][c]["err_mv"]) for r in rows for c in CODES)
    cu_min = min(r["cu_elec_ff"] for r in rows)
    cu_max = max(r["cu_elec_ff"] for r in rows)

    netlist_sha = evidence.sha256_file(FRAGMENT)
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, FRAGMENT)

    process_corners_run = sorted({c["process"] for c in corners})
    temps_run = sorted({float(c["temperature_c"]) for c in corners})
    supplies_run = sorted({float((c.get("params") or {}).get("vdd_val")) for c in corners})

    lines: list[str] = []
    a = lines.append
    a(f"# Record {record_id}")
    a("")
    a(f"- **Record ID**: {record_id}")
    a(
        "- **Claim**: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- "
        "grades the RATIFIED `V_REF = V_DD` row's own content as a machine-"
        "evaluated relation at every corner of the ratified corner set: the "
        "applied reference at the CDAC (`v(vrefp)-v(vrefn)`) equals the "
        "corner's own rail (`v(vdd)`) within solver/print precision only "
        "(envelope measurement `vref_ratio`, `spec_row: v_ref`, limits "
        "1 +/- 1e-5 relative; VREFN pinned to 0 within 1e-5 V). Reports, and "
        "deliberately does NOT grade, the other two ratified rows this "
        "experiment touches: LSB (per-corner differential step deviation -- "
        "no ratified tolerance, decision owned by "
        "spec/decision-records/DR-026-cdac-row-tolerance-decisions.md, "
        "proposed) and Sampling cap (structural plate geometry re-checked "
        "exactly; electrical C_u observed via reference charge, same "
        "missing-tolerance decision)."
    )
    a(
        "- **Netlist provenance**: same DUT as the pilot request -- "
        "`sim/cdac-array-transfer/testbench/klt/tb_body.spice` (two-line "
        "wrapper) `.include`ing the hand-authored "
        "`sim/cdac-array-transfer/testbench/tb_cdac_array_transfer.spice` "
        "(which matches `design/cdac/cdac_array.sch`'s unit-cell pattern "
        "and sizing). Request: `sim/cdac-array-transfer/testbench/klt/"
        "request-graded.json` (sha256 "
        f"`{request_sha256}`); analysis tran step 0.05n "
        "(finer than the pilot's 0.5n so the reference-charge integral "
        "resolves the ~0.2 n switching event; the settled t=500n FIND "
        "values can still shift at the last printed digit -- see the "
        "baseline-agreement probe below)."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(corners)
        )
    )
    a(
        f"- **Structural check**: run_transfer.check_structural_sizing() on the "
        f"committed fragment -- {'PASS' if struct_ok else 'FAIL: ' + '; '.join(struct_problems)} "
        f"(ratified: cap_mim_m3_1 W=L={run_transfer.RATIFIED_UNIT_CAP_WL_UM:.4f} um, "
        f"weights {run_transfer.RATIFIED_BINARY_WEIGHTS}+"
        f"{run_transfer.RATIFIED_TERMINATION_WEIGHT}(term)="
        f"{run_transfer.RATIFIED_ARRAY_SIZE_PER_SIDE}/side). This is the "
        "sampling-cap row's exact structural part; it is corner-invariant."
    )
    graded_verdict = f"PASS at all {len(rows)} corners" if graded_ok else "FAIL"
    a(
        "- **Graded check (V_REF)**: envelope `vref_ratio` and `v_vrefn`, "
        f"`spec_row: v_ref` -- {graded_verdict}. "
        "At six significant digits the print step just above "
        "unity is 1e-5 (1.00000 to 1.00001). The relative allowance of 1e-5 "
        "is twice the 5e-6 half-step and corresponds to >= 16x "
        "ngspice's default vntol=1e-6 V at the 1.62 V rail corner; it is a "
        "solver-precision bound on an exact relation (DR-003's `V_REF = "
        "V_DD`), NOT a design tolerance. No LSB or sampling-cap pass "
        "condition exists in this envelope: neither row has a ratified "
        "tolerance on its measured deviation (DR-026, proposed), so their "
        "observables here carry no limits and no spec_row tag."
    )
    a(
        "- **Functional check**: strict monotonicity (vdiff strictly "
        "increasing with code) AND correct polarity (code 0 < 0 < code 511) "
        f"at every corner -- {'PASS' if functional_ok else 'FAIL'} (the "
        "envelope's four untagged `mono_step_*` limits-bearing measurements "
        "machine-check the same relation; they carry no spec_row tag so "
        "they cannot be read as any row's coverage)."
    )
    a(
        "- **Informational (no ratified tolerance -> not graded)**: max "
        f"sampled voltage-level error |vdiff - ideal| = {max_err_mv:.4f} mV across "
        "corners/codes. The table separately gives the largest relative interval "
        "error at each corner, comparing each measured voltage difference with "
        "the ideal difference at its two codes (spans of 128, 128, 128 and 127 codes). The "
        "per-corner LSB derived from the graded reference "
        "(`2*(v_vrefp-v_vrefn)/2^N`) and per-corner electrical unit cap "
        "from the reference charge are tabulated below. The electrical C_u "
        "derivation: q_vrefp integrates i(Vrefp) over the whole transient; "
        "the exact switched-unit equivalent of the five-code set is "
        f"{SWITCHED_UNITS_EQ:.9f} positions (per side with sw switched "
        "units, charge drawn = C_u*vdd*sw*(1 - sw/512) -- the floating top "
        "plate's redistribution returns the rest), so cu_elec = "
        f"|q_vrefp|/(vdd*{SWITCHED_UNITS_EQ:.9f}). Measured range "
        f"{cu_min:.4f} - {cu_max:.4f} fF vs the ratified `C_u ~= 8.66 fF` "
        "(a model '≈' figure): the delta includes switch channel-charge "
        "injection and crowbar, is corner-dependent, and is exactly the "
        "quantity DR-026 exists to bound."
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Binding corner**: `{binding['corner_id']}` (max |vref_ratio - 1| = "
        f"{abs(binding['vref_ratio'] - 1.0):.3g}) -- recorded regardless of "
        "pass/fail, per sim/README.md's per-row binding-corner convention."
    )
    a(
        f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} (envelope status "
        f"{report.get('status')!r}, {report.get('passed')}/{report.get('corner_count')} "
        "corners passed; graded V_REF relation + structural census + "
        "functional monotonicity all as stated above)"
    )
    a("")
    a("## `klt sim` run")
    a("")
    jobs = info.get("jobs") or []
    a(
        f"- backend resolved: {info.get('resolved_backend')}; "
        f"{len(jobs)} job(s); "
        + (f"job `{jobs[0]['job_id']}` state `{jobs[0]['state']}` exit "
           f"`{jobs[0]['exit_code']}` elapsed {jobs[0]['elapsed_seconds']}s; "
           if len(jobs) == 1 and jobs[0].get("job_id") else "")
        + f"runner klt {jobs[0].get('runner_klt_version') if jobs else '?'} / "
        f"client {jobs[0].get('client_klt_version') if jobs else '?'} "
        f"({jobs[0].get('runner_compatibility') if jobs else '?'})"
    )
    a(f"- worker ngspice: {worker_ng}; worker PDK: {worker_pdk}")
    a(
        f"- raw outputs: [report.json](../klt-sim/{raw_run_id}/report.json) "
        f"and [per-corner artifacts](../klt-sim/{raw_run_id}/out/)"
    )
    a("")
    a("## Per-corner results")
    a("")
    a("| corner-id | vref_ratio (status) | v_vrefn V (status) | LSB derived mV | max step dev % | cu_elec fF | monotonic | polarity | min gap V |")
    a("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        a(
            f"| `{r['corner_id']}` | {r['vref_ratio']:.6g} ({r['vref_ratio_status']}) "
            f"| {r['v_vrefn']:.6g} ({r['v_vrefn_status']}) | {r['lsb_derived_mv']:.4f} "
            f"| {r['step_dev_pct']:.3f} | {r['cu_elec_ff']:.4f} "
            f"| {'YES' if r['monotonic'] else 'NO'} | {'YES' if r['correct_sign'] else 'NO'} "
            f"| {r['min_gap']:.6g} |"
        )
    a("")
    a("## Baseline-agreement probe (informational)")
    a("")
    if cmp_res.get("passed"):
        a(
            f"- compare_klt_envelope.py vs record `{BASELINE_RECORD}`: PASS "
            f"({cmp_res.get('pairs_compared', '?')} pairs, max |delta| "
            f"{cmp_res.get('max_abs_delta_v') or 0:.3g} V)"
        )
    else:
        a(
            f"- compare_klt_envelope.py vs record `{BASELINE_RECORD}`: FAIL "
            "under the pilot's |delta| <= 2e-5 V rule "
            f"({cmp_res.get('pairs_compared', '?')} pairs, max |delta| "
            f"{cmp_res.get('max_abs_delta_v') or float('nan'):.3g} V). That rule "
            "is issue #811's gate, not a spec value: it is reported, not "
            "widened or reinterpreted. This run differs from the baseline in "
            f"PDK pin (worker {worker_pdk.rpartition(' @ ')[2][:8]}... vs baseline "
            f"{_baseline_pdk_commit(BASELINE_RECORD)[:8]}...), host, "
            "ngspice build, and tran step (0.05n here vs 0.5n) -- none "
            "separated; the pilot record 20261106-190301-7bdf8c4 saw the "
            "same failure mode at `ff_27c_1.80v` (3e-05 V) with the "
            "baseline-matching 0.5n step, so the step is not its cause."
        )
    a("")
    lines.extend(evidence.environment_block(
        pdk_line=worker_pdk,
        ngspice_line=worker_ng,
        netlist_sha256=netlist_sha,
        extra={
            "klt (client)": str(
                (jobs[0] or {}).get("client_klt_version", "unknown") if jobs else "unknown"
            ),
        },
    ))
    a("")
    lines.extend(
        evidence.footer_lines(
            "sim/cdac-array-transfer/run_klt_graded.py --record", supersedes
        )
    )

    record_path.write_text("\n".join(lines))
    return record_path, overall_ok, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true",
                    help="submit the graded request and mint the evidence record")
    ap.add_argument("--backend", default=None,
                    help="klt sim backend (default: klt's own / $KLT_SIM_BACKEND)")
    ap.add_argument("--request", default=str(REQUEST),
                    help="full-grid records require the committed request-graded.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--supersedes", default="")
    args = ap.parse_args(argv)

    if not args.record:
        ap.print_usage()
        print("nothing to do: pass --record (this runner has no --check-env; "
              "the submit itself fails loudly on a missing PDK or klt)")
        return 2

    request = Path(args.request).resolve()
    if request != REQUEST:
        print(f"REFUSING to mint full-grid evidence from {request}. "
              f"Use {REQUEST.name} for --record or klt sim for a debug request.")
        return 3
    try:
        request_sha256 = _graded_request_sha256()
    except ValueError as exc:
        print(f"REFUSING to submit {request}: {exc}")
        return 3
    record_id = evidence.new_record_id()
    stderr_path = EXPERIMENT_DIR / "klt-sim" / record_id / "client-stderr.txt"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    report, info = run(args.backend, request, record_id, stderr_path)
    record_path, ok, problem = write_record(
        report, info, record_id, request_sha256=request_sha256, raw_run_id=record_id,
        note=args.note, supersedes=args.supersedes,
    )
    if problem:
        print(f"REFUSING to mint {record_path}: {problem}")
        print(f"raw outputs kept under sim/cdac-array-transfer/klt-sim/{record_id}/ "
              "for hand triage (do not commit an unpinnable record)")
        return 3
    print(f"wrote {record_path}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

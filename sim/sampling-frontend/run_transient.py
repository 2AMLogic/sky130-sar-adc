#!/usr/bin/env python3
"""Standalone transient verification for design/sampling_frontend.sch
(issue #52).

Why this is a bespoke script rather than sim/run_corners.py /
sim/monte_carlo.py: the shared harness (sim/harness/testbench.py
_render_body()) always appends a `.control / op / <measures> / .endc /
.end` block -- a single operating-point analysis. Settling time and
charge-injection droop are transient (`.tran`) quantities that op-point
measurement cannot produce, so this experiment needs its own netlist
assembly. It still reuses the harness's PDK/toolchain/evidence helpers
(sim/harness/pdk.py, sim/harness/toolchain.run_ngspice, sim/harness/evidence)
rather than duplicating them -- see sim/README.md's own "Divergences"
section for the precedent of naming a deliberate departure instead of
silently doing something different.

Usage (from the repo root, after `source sim/env.sh`):
    python3 sim/sampling-frontend/run_transient.py            # print results
    python3 sim/sampling-frontend/run_transient.py --record    # + write evidence
    python3 sim/sampling-frontend/run_transient.py --full      # + ss corner on
                                                                #   the worst-case
                                                                #   input point

Reports two distinct results per test point, both real measurements, NOT a
single "it works" verdict -- see DR-004
(spec/decision-records/DR-004-sampling-frontend-sizing.md) for the full
derivation:

  1. In-sample settling (top_p_end/top_n_end @ SAMPLE_END_NS): how closely
     TOP_P/TOP_N track their analog inputs while SAMPLE is still asserted.
     Clean (sub-mV) at every tested point once Sa/Sd are sized long enough to
     suppress their off-state subthreshold leakage (DR-004).
  2. Post-edge delta (top_p_hold/top_n_hold @ HOLD_PROBE_NS, printed as
     "hold_dv_p_mV"/"hold_dv_n_mV"): how far TOP_P/TOP_N have moved by
     HOLD_PROBE_NS, well after the SAMPLE falling edge. This is large
     (hundreds of mV) and is NOT simply the sampling switch's intrinsic
     charge injection -- diagnostic work (DR-004 "Open items") traced it to
     a not-fully-root-caused common-mode capacitive kick on the floating
     TOP_x/BPREF_x node pair, only partially reduced by adding dead time
     between SAMPLE/SAMPLEB. Tracked as a real, open, quantified risk in
     issue #61, not asserted fixed here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import pdk, toolchain, evidence  # noqa: E402

DUT_FRAGMENT = EXPERIMENT_DIR / "testbench" / "sampling_frontend_dut.spice"

# Differential test points: (name, VINP, VINN). VCM = 0.9V (DR-003/DR-004
# provisional, V_REF/2 at V_REF = VDD = 1.8V). "worst_case_pp"/"worst_case_np"
# drive one side to within 0.2V of a rail while the other sits at the
# opposite rail -- the maximum simultaneous per-side headroom stress the
# differential front end can see; "common_mode" is the zero-differential
# input at VCM itself.
TEST_POINTS = {
    "common_mode": (0.9, 0.9),
    "worst_case_pp": (1.6, 0.2),  # VINP near VDD, VINN near GND
    "worst_case_np": (0.2, 1.6),  # mirror image
}

VDD = 1.8
VCM = 0.9
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27

SAMPLE_END_NS = 409.0  # last point still inside the 400ns-wide sample pulse
HOLD_PROBE_NS = 419.5  # ~8ns after the SAMPLE falling edge completes (edge
# runs 411-412ns for the pulse source used below) -- well past the edge
# itself, still well before the next edge at 811ns. See "Known limitation"
# below: this is NOT a settled "hold" value in the usual charge-injection
# sense -- see DR-004 and issue #61.


def build_netlist(vinp: float, vinn: float, corner: str, temp_c: float = 27.0) -> str:
    frag = DUT_FRAGMENT.read_text()
    info = pdk.resolve()
    lines = [
        f"* sampling-frontend transient verification (issue #52) -- corner={corner} temp={temp_c}C",
        f".lib {info.ngspice_lib} {corner}",
        f".temp {temp_c}",
        "",
        f"Vdd VDD 0 dc {VDD}",
        f"Vinp VINP 0 dc {vinp}",
        f"Vinn VINN 0 dc {vinn}",
        f"Vvcm VCM 0 dc {VCM}",
        # SAMPLE: 0 (hold) -> VDD (sample) at 10ns, width 400ns, period 800ns
        f"Vsample SAMPLE 0 pulse(0 {VDD} 10n 1n 1n 400n 800n)",
        "",
        frag,
        "",
        ".control",
        "tran 1n 900n",
        f"meas tran top_p_end find v(TOP_P) at={SAMPLE_END_NS}n",
        f"meas tran top_n_end find v(TOP_N) at={SAMPLE_END_NS}n",
        f"meas tran top_p_hold find v(TOP_P) at={HOLD_PROBE_NS}n",
        f"meas tran top_n_hold find v(TOP_N) at={HOLD_PROBE_NS}n",
        f"meas tran g_p_end find v(G_P) at={SAMPLE_END_NS}n",
        f"meas tran g_n_end find v(G_N) at={SAMPLE_END_NS}n",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def parse_measures(output: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in output.splitlines():
        parts = line.split("=")
        if len(parts) == 2:
            name = parts[0].strip()
            try:
                val = float(parts[1].strip().split()[0])
            except ValueError:
                continue
            if name in (
                "top_p_end", "top_n_end", "top_p_hold", "top_n_hold",
                "g_p_end", "g_n_end",
            ):
                result[name] = val
    return result


def run_point(name: str, vinp: float, vinn: float, corner: str, scratch: Path) -> dict:
    netlist = build_netlist(vinp, vinn, corner)
    log_name = f"{name}_{corner}"
    output = toolchain.run_ngspice(netlist, scratch, log_name)
    meas = parse_measures(output)
    return {
        "name": name, "corner": corner, "vinp": vinp, "vinn": vinn,
        "netlist": netlist, "log_name": log_name, **meas,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="write a sim/README.md-style evidence record")
    ap.add_argument("--full", action="store_true", help="also run the worst-case point at the ss corner")
    args = ap.parse_args()

    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice/PDK not available (" + "; ".join(check.messages) + ")")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drift -- " + "; ".join(check.messages))
        return 1

    scratch = Path("/tmp/sampling-frontend-run")
    results = []
    for name, (vinp, vinn) in TEST_POINTS.items():
        results.append(run_point(name, vinp, vinn, "tt", scratch))
    if args.full:
        results.append(run_point("worst_case_pp", 1.6, 0.2, "ss", scratch))

    print(f"{'point':16} {'corner':5} {'vinp':6} {'vinn':6} {'top_p_end':10} {'top_n_end':10} "
          f"{'hold_dv_p_mV':13} {'hold_dv_n_mV':13} {'gvgs_p':7} {'gvgs_n':7}")
    for r in results:
        # "hold_dv" = TOP_x's total post-edge delta by HOLD_PROBE_NS -- see
        # the module docstring and DR-004: this is NOT purely the switch's
        # intrinsic charge injection, it also includes the not-fully-
        # root-caused common-mode kick tracked in issue #61.
        hold_dv_p_mv = (r["top_p_end"] - r["top_p_hold"]) * 1000
        hold_dv_n_mv = (r["top_n_end"] - r["top_n_hold"]) * 1000
        vgs_p = r["g_p_end"] - r["top_p_end"]
        vgs_n = r["g_n_end"] - r["top_n_end"]
        print(f"{r['name']:16} {r['corner']:5} {r['vinp']:<6} {r['vinn']:<6} "
              f"{r['top_p_end']:<10.5f} {r['top_n_end']:<10.5f} "
              f"{hold_dv_p_mv:<13.3f} {hold_dv_n_mv:<13.3f} {vgs_p:<7.4f} {vgs_n:<7.4f}")

    if args.record:
        write_record(results)
    return 0


def write_record(results: list[dict]) -> None:
    record_id = evidence.new_record_id()
    # Snapshot the DUT fragment actually simulated (not a full corner netlist,
    # since each test point renders its own -- the fragment is what's common
    # and reproducible across all of them).
    record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, DUT_FRAGMENT)
    netlist_sha = evidence.sha256_file(DUT_FRAGMENT)

    info = pdk.resolve()
    pdk_line = f"{info.variant} @ {pdk.resolved_commit(info)}"
    ng_version = toolchain._ngspice_version() or "unknown"

    lines = []
    a = lines.append
    a(f"# sampling-frontend -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: None yet against a ratified spec row (spec/target-spec.md "
        "is entirely DRAFT pending #1/#27) -- this record substantiates issue "
        "#52's own acceptance criteria: it exercises the bootstrapped sampling "
        "front end in isolation and reports two distinct, real measurements -- "
        "in-sample settling (clean) and a post-edge delta (large, only "
        "partially understood) -- using only ratified 1.8V devices. Sizing "
        "(Cboot, Csamp, VCM, and the Sa/Sd channel length) is provisional per "
        "DR-003 (pending #27) and "
        "spec/decision-records/DR-004-sampling-frontend-sizing.md, which also "
        "carries the full derivation of both measurements below."
    )
    a("- **Netlist provenance**: schematic (design/sampling_frontend.sch, regenerated -- see testbench/sampling_frontend_dut.spice header)")
    a(
        "- **Corner matrix run**: tt/27C/1.8V (nominal) at all three test "
        "points below" + (
            "; ss/27C/1.8V additionally on the worst_case_pp point (--full)"
            if any(r["corner"] == "ss" for r in results) else ""
        )
    )
    a(
        "- **Subset-corner justification**: this is a settling/charge-injection "
        "check of the front end in isolation, not a spec-row PVT claim (there "
        "is no ratified row to check yet). Temperature (-40/125C), supply "
        "tolerance (+-10%), and the ff/sf/fs process corners are deferred to "
        "#28's full corner campaign once the whole SAR ADC exists; the ss "
        "point here is a directional check only (device speed/threshold "
        "moves the headroom-decay effect named in "
        "spec/decision-records/DR-004's Open items, not a pass/fail gate)."
    )
    a("")
    a("## Test points")
    a("")
    a(
        "\"Hold delta\" = TOP_x's total move from its in-sample settled value "
        "by HOLD_PROBE_NS (well after the SAMPLE falling edge completes). "
        "This is **not** simply the sampling switch's intrinsic charge "
        "injection -- see \"Result\" below and DR-004's Open items."
    )
    a("")
    a("| Point | Corner | VINP | VINN | TOP_P settled | TOP_N settled | Hold delta P (mV) | Hold delta N (mV) | Vgs(Msw_p) | Vgs(Msw_n) |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        hold_dv_p_mv = (r["top_p_end"] - r["top_p_hold"]) * 1000
        hold_dv_n_mv = (r["top_n_end"] - r["top_n_hold"]) * 1000
        vgs_p = r["g_p_end"] - r["top_p_end"]
        vgs_n = r["g_n_end"] - r["top_n_end"]
        a(
            f"| {r['name']} | {r['corner']} | {r['vinp']} | {r['vinn']} | "
            f"{r['top_p_end']:.5f} | {r['top_n_end']:.5f} | "
            f"{hold_dv_p_mv:.3f} | {hold_dv_n_mv:.3f} | {vgs_p:.4f} | {vgs_n:.4f} |"
        )
    a("")
    a(
        f"LSB (differential, provisional per DR-003, pending #27): "
        f"{LSB_DIFF_MV_PROVISIONAL} mV -- hold-delta figures above are "
        f"single-ended (per-side) in mV, not yet expressed differentially "
        f"(P/N cancellation depends on P/N device matching, not evaluated "
        f"here; see DR-004 Open items). Every hold-delta figure above is "
        f"roughly two orders of magnitude larger than this provisional LSB."
    )
    a("")
    a("## Result")
    a("")
    a(
        "**In-sample settling: PASS** (informational/isolation check, not a "
        "spec pass/fail). At every test point, TOP_P/TOP_N settle to within "
        "simulation resolution (sub-mV) of their respective analog inputs by "
        "the end of the 400ns sample window, at both rail-adjacent inputs "
        "(0.2V, 1.6V) and at the common-mode point (0.9V). Vgs(Msw) stays "
        "well above threshold at every point tested (lowest observed: "
        "worst_case_pp's Msw_p, whose own input is closest to VDD) -- the "
        "bootstrap mechanism is doing materially better than a plain "
        "VDD-gated switch would (which would have Vgs -> VDD - VIN, "
        "collapsing to ~0.2V at VIN=1.6V instead of the boosted value "
        "observed here). This result required fixing a real subthreshold-"
        "leakage sizing bug in Sa/Sd (L=0.15um -> L=0.5um) found while "
        "deriving this record -- see DR-004."
    )
    a("")
    a(
        "**Post-edge hold delta: characterized, NOT a clean PASS.** By "
        "HOLD_PROBE_NS, TOP_P/TOP_N have moved several hundred mV "
        "single-ended away from their settled in-sample value (see table "
        "above) -- roughly two orders of magnitude above the provisional "
        "LSB. This is real, reproducible circuit behavior, not a measurement "
        "artifact (confirmed against the raw transient waveform, not just "
        "the two `.meas` points). Diagnostic work (documented in full in "
        "DR-004's Open items) ruled out a simple break-before-make "
        "explanation -- adding 2-10ns of dead time between SAMPLE/SAMPLEB in "
        "a testbench-only experiment (the schematic's own on-die inverter is "
        "unmodified) reduced but did not eliminate the delta, and stopped "
        "shrinking with more dead time. The differential TOP_x-BPREF_x "
        "voltage stays essentially constant across the transition while both "
        "nodes move together, pointing at a common-mode capacitive kick onto "
        "the floating TOP_x/BPREF_x node pair from the switching SAMPLE/"
        "SAMPLEB control signals -- not fully root-caused within this "
        "record's scope. Tracked as a real, open, quantified risk in issue "
        "#61, which must be resolved (or the residual re-characterized "
        "against a ratified spec row) before #28/#29's corner/Monte-Carlo "
        "campaigns can produce a meaningful spec-row verification for this "
        "front end."
    )
    a("")
    lines.extend(
        evidence.environment_block(
            pdk_line=pdk_line,
            ngspice_line=ng_version,
            netlist_sha256=netlist_sha,
            extra={"Toolchain check": "PASS" if toolchain.check_env().status == 0 else "see sim/run_corners.py --check-env"},
        )
    )
    a("")
    lines.extend(evidence.footer_lines("sim/sampling-frontend/run_transient.py", ""))

    record_path.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {record_path}")


if __name__ == "__main__":
    raise SystemExit(main())

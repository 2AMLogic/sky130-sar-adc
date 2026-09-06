#!/usr/bin/env python3
"""Standalone behavioral testbench runner for design/sar_sequencer.sch
(issue #55).

Cold-start invocation (see docs/environment-setup.md for the one-time
toolchain/PDK bootstrap this assumes):

    source sim/env.sh                                          # export PDK_ROOT / PDK
    python3 sim/sar-sequencer-behavioral/run_testbench.py --check-env
    python3 sim/sar-sequencer-behavioral/run_testbench.py       # run + print PASS/FAIL, no evidence written
    python3 sim/sar-sequencer-behavioral/run_testbench.py --record  # also mint an evidence record
    python3 sim/sar-sequencer-behavioral/run_testbench.py --corners --record
        # full ratified PVT corner sweep (issue #28) -- see run_corner_campaign()

Exercises the SAR sequencer + clock/phase generator (design/sar_sequencer.sch)
against an ideal comparator-decision stimulus (sim/sar-sequencer-behavioral/
testbench/sar_sequencer_tb_fragment.spice) with NO dependency on the front
end, CDAC array, or comparator -- issue #55's own scope. Verifies:

  1. Correct bit-by-bit (MSB-first), successive-approximation capture of two
     different fixed target codes across two full back-to-back conversions.
  2. Correct clock/phase timing (each of the 11 one-hot ring phases asserted
     during, and only during, its own designated CLK period).
  3. The ring sequencer's auto-restart (cycle 2 begins with no external start
     pulse, exactly (N+2) CLK periods after cycle 1).

Divergence from sim/run_corners.py / sim/monte_carlo.py (documented per
sim/README.md's "divergences, each deliberate" convention): those two
runners' shared `.control` block only supports `.op` analysis (see
sim/harness/testbench.py's module docstring). This is a transient/digital
sequencing check, so this script assembles and runs its own `.tran` deck
directly, reusing sim/harness's pdk/toolchain/measure/evidence modules for
everything PVT-machinery-independent (PDK resolution, the ngspice
invocation + timeout, `name = value` log parsing, and the evidence-record
scaffolding).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, measure, pdk, toolchain  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = evidence.REPO_ROOT
DESIGN_SCH = REPO_ROOT / "design" / "sar_sequencer.sch"
XSCHEMRC = REPO_ROOT / "sim" / "xschemrc"
FRAGMENT = EXPERIMENT_DIR / "testbench" / "sar_sequencer_tb_fragment.spice"

# --- Ratified corner-set axes (issue #28), per spec/target-spec.md's
# "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply,
# sky130 process corners. NOMINAL_SUPPLY_V = 1.8V is the ratified V_REF/V_DD
# value (DR-003 Item 1), not a provisional planning constant.
NOMINAL_SUPPLY_V = 1.8
SUPPLY_TOLERANCE = 0.10
TEMPS_C = [-40, 27, 125]
PROCESS_CORNERS = ["tt", "ss", "ff", "sf", "fs"]

# Expected value (digital 1/0) for every `.meas` name in the fragment --
# derived by hand from the same CODE1/CODE2 target codes and phase/timing
# schedule documented in the fragment's own header comment. Kept in lockstep
# with that file; if the fragment's stimulus changes, this table must too.
CODE1 = [1, 1, 0, 0, 1, 0, 1, 0, 1, 1]  # b9..b0
CODE2 = [0, 0, 1, 1, 0, 1, 0, 1, 0, 0]  # b9..b0


def _expected_bits() -> dict[str, int]:
    expected: dict[str, int] = {}
    for c, full in ((1, True), (2, False)):
        if full:
            expected[f"phsample_c{c}"] = 1
        labels = [f"b{9 - i}" for i in range(10)] + ["eoc"]
        for lab in labels:
            if full or lab in ("b9", "eoc"):
                expected[f"ph{lab}_c{c}"] = 1
    for c, code in ((1, CODE1), (2, CODE2)):
        for i, bit in enumerate(code):
            b = 9 - i
            expected[f"dout{b}_c{c}"] = bit
    expected["dout9_early_c1"] = CODE1[0]
    return expected


EXPECTED_BITS = _expected_bits()
DIGITAL_THRESHOLD_V = 0.9  # midpoint of the 1.8 V rail; ample margin either side


def netlist_dut(scratch_dir: Path) -> Path:
    """Netlist design/sar_sequencer.sch with xschem (headless), returning the
    path to the generated .spice file. Raises RuntimeError on any xschem
    error/nonzero exit -- this is also issue #55's own "opens/builds cleanly"
    acceptance check, run fresh on every invocation rather than trusting a
    stale snapshot."""
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "xschem", "-x", "-n", "-s", "-q",
        "--rcfile", str(XSCHEMRC),
        "-o", str(scratch_dir),
        str(DESIGN_SCH),
    ]
    # Shares its timeout budget with toolchain.run_ngspice()'s own ngspice
    # invocations (issue #133) rather than a second hardcoded literal here,
    # so SIM_NGSPICE_TIMEOUT_S raises both this step's and the .tran run's
    # budget together on a slower-but-still-progressing host.
    timeout_s = toolchain.toolchain_timeout_s()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"xschem netlisting of {DESIGN_SCH} timed out after {timeout_s:g}s. "
            f"If xschem was still making progress (not hung), raise the budget "
            f"with e.g. {toolchain.TIMEOUT_ENV_VAR}=300 (seconds) in the "
            f"environment before re-running."
        ) from exc
    out_path = scratch_dir / "sar_sequencer.spice"
    if proc.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"xschem netlisting of {DESIGN_SCH} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return out_path


def assemble_deck(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    process_corner: str = "tt",
    temp_c: float = 27.0,
    supply_v: float = NOMINAL_SUPPLY_V,
) -> str:
    stdcell_spice = pdk_info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    if not stdcell_spice.is_file():
        raise RuntimeError(f"sky130_fd_sc_hd combined SPICE deck not found at {stdcell_spice}")

    dut_lines = [ln for ln in dut_netlist_text.splitlines() if ln.strip() != ".end"]
    fragment_text = FRAGMENT.read_text()

    lines = [
        "* sar-sequencer-behavioral -- standalone testbench (issue #55/#28), NOT",
        "* routed through sim/run_corners.py / sim/monte_carlo.py -- see this",
        "* experiment's own record for the divergence from the shared PVT/MC",
        "* harness (its .control block only supports .op analysis).",
        f"* corner={process_corner} temp={temp_c}C supply={supply_v}V",
        f".lib {pdk_info.ngspice_lib} {process_corner}",
        f".temp {temp_c}",
        f".param vdd_val = {supply_v}",
        f".include {stdcell_spice}",
        "",
        *dut_lines,
        "",
        fragment_text,
        ".end",
    ]
    return "\n".join(lines) + "\n"


def run(record: bool) -> int:
    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice or the pinned PDK is not installed on this machine.")
        for m in check.messages:
            print(f"  {m}")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        for m in check.messages:
            print(f"  {m}")
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    pdk_info = pdk.resolve()

    with tempfile.TemporaryDirectory(prefix="sar-sequencer-tb-") as scratch:
        scratch_dir = Path(scratch)

        dut_path = netlist_dut(scratch_dir)
        dut_text = dut_path.read_text()
        print(f"OK: {DESIGN_SCH.relative_to(REPO_ROOT)} netlisted cleanly ({dut_path}).")

        non_hd = [
            ln for ln in dut_text.splitlines() if ln.strip().startswith("x") and "sky130_fd_sc_hd__" not in ln
        ]
        if non_hd:
            print("FAIL: instance(s) not resolving to sky130_fd_sc_hd found in the DUT netlist:")
            for ln in non_hd:
                print(f"  {ln}")
            return 1
        n_instances = len([ln for ln in dut_text.splitlines() if ln.strip().startswith("x")])
        print(f"OK: all {n_instances} standard-cell instances resolve to sky130_fd_sc_hd (0 other-library matches).")

        deck_text = assemble_deck(dut_text, pdk_info)
        output = toolchain.run_ngspice(deck_text, scratch_dir, "sar_sequencer_tb")

        parsed = measure.parse(output, list(EXPECTED_BITS.keys()))
        missing = measure.missing(parsed, list(EXPECTED_BITS.keys()))
        if missing:
            print(f"FAIL: {len(missing)} measurement(s) missing from ngspice output: {missing}")
            return 1

        rows = []
        all_pass = True
        for name in sorted(EXPECTED_BITS):
            expected_bit = EXPECTED_BITS[name]
            measured_v = parsed[name]
            measured_bit = 1 if measured_v > DIGITAL_THRESHOLD_V else 0
            ok = measured_bit == expected_bit
            all_pass = all_pass and ok
            rows.append((name, expected_bit, measured_v, "PASS" if ok else "FAIL"))
            status = "PASS" if ok else "FAIL"
            print(f"{status}: {name}: expected={expected_bit} measured={measured_v:.4f}V")

        print()
        print("OVERALL: PASS" if all_pass else "OVERALL: FAIL")

        if record:
            record_id = evidence.new_record_id()
            record_path = evidence.write_netlist_snapshot(EXPERIMENT_DIR, record_id, dut_path)
            runs_dir = EXPERIMENT_DIR / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            (runs_dir / f"{record_id}.log").write_text(output)

            net_sha = evidence.sha256_file(dut_path)
            lines = [
                f"# Record {record_id}",
                "",
                f"- **Record ID**: {record_id}",
                "- **Claim**: `spec/decision-records/DR-006-sar-sequencer-bit-count-and-timing-budget.md` "
                "(provisional N=10 bit-count and 1.2-12 MHz timing budget) -- behavioral sequencing "
                "correctness only, pending #27; not a PVT-corner or Monte-Carlo claim.",
                "- **Netlist provenance**: schematic (`design/sar_sequencer.sch`)",
                "- **Divergence from the shared PVT/MC harness**: this experiment does not run through "
                "`sim/run_corners.py`/`sim/monte_carlo.py` (their shared `.control` block only supports "
                "`.op` analysis; this is a transient/digital sequencing check) -- see "
                "`sim/sar-sequencer-behavioral/run_testbench.py`'s own module docstring.",
                f"- **Stimulus**: ideal comparator-decision (`COMP_OUT`) PWL, two back-to-back "
                f"conversions, CODE1(b9..b0)={''.join(str(b) for b in CODE1)}b, "
                f"CODE2(b9..b0)={''.join(str(b) for b in CODE2)}b -- see "
                "`sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`.",
                f"- **Overall**: {'PASS' if all_pass else 'FAIL'}",
                "",
                "## Per-check results",
                "",
                "| check | expected (bit) | measured (V) | pass/fail |",
                "|---|---|---|---|",
            ]
            for name, expected_bit, measured_v, status in rows:
                lines.append(f"| `{name}` | {expected_bit} | {measured_v:.4f} | {status} |")
            lines.append("")
            lines.extend(
                evidence.environment_block(
                    pdk_line=f"{pdk_info.variant} @ {pdk.resolved_commit(pdk_info)}",
                    ngspice_line=toolchain._ngspice_version() or "unknown",
                    netlist_sha256=net_sha,
                )
            )
            lines.append("")
            lines.extend(evidence.footer_lines("sim/sar-sequencer-behavioral/run_testbench.py", ""))
            record_path.write_text("\n".join(lines))
            print(f"\nRecord written: {record_path.relative_to(REPO_ROOT)}")

        return 0 if all_pass else 1


def run_corner_campaign(record: bool, quiet: bool = False) -> int:
    """Full ratified-corner-set sweep (issue #28): re-runs the exact same
    behavioral sequencing check `run()` performs, but across the OAT PVT
    grid built from the ratified corner set (spec/target-spec.md's
    "Numeric rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10%
    supply, sky130 process corners), substantiating spec/target-spec.md's
    ratified `Resolution N` row (N=10, confirmed functionally correct
    bit-by-bit capture at every bound corner) rather than DR-006's
    provisional claim alone. The DUT is netlisted with xschem ONCE (a
    property of the schematic, not of any PVT point) and re-simulated once
    per corner point."""
    check = toolchain.check_env()
    if check.status == 3:
        print("SKIP: ngspice or the pinned PDK is not installed on this machine.")
        for m in check.messages:
            print(f"  {m}")
        return 0
    if check.status == 1:
        print("FAIL: toolchain drifted from sim/toolchain.json pin.")
        for m in check.messages:
            print(f"  {m}")
        return 1
    for w in check.warnings:
        print(f"WARNING: {w}")

    pdk_info = pdk.resolve()

    with tempfile.TemporaryDirectory(prefix="sar-sequencer-corners-") as scratch:
        scratch_dir = Path(scratch)
        dut_path = netlist_dut(scratch_dir)
        dut_text = dut_path.read_text()
        print(f"OK: {DESIGN_SCH.relative_to(REPO_ROOT)} netlisted cleanly ({dut_path}).")

        non_hd = [
            ln for ln in dut_text.splitlines() if ln.strip().startswith("x") and "sky130_fd_sc_hd__" not in ln
        ]
        if non_hd:
            print("FAIL: instance(s) not resolving to sky130_fd_sc_hd found in the DUT netlist:")
            for ln in non_hd:
                print(f"  {ln}")
            return 1

        grid = corners_mod.ratified_oat_grid(
            NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )

        points = []
        for process_corner, temp_c, supply_v in grid:
            cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
            deck_text = assemble_deck(dut_text, pdk_info, process_corner, temp_c, supply_v)
            output = toolchain.run_ngspice(deck_text, scratch_dir, f"sar_sequencer_tb_{cid}")

            digital_threshold_v = 0.5 * supply_v
            parsed = measure.parse(output, list(EXPECTED_BITS.keys()))
            missing = measure.missing(parsed, list(EXPECTED_BITS.keys()))
            rows = []
            all_pass = not missing
            for name in sorted(EXPECTED_BITS):
                if name in missing:
                    rows.append((name, EXPECTED_BITS[name], None, "FAIL (missing)"))
                    continue
                expected_bit = EXPECTED_BITS[name]
                measured_v = parsed[name]
                measured_bit = 1 if measured_v > digital_threshold_v else 0
                ok = measured_bit == expected_bit
                all_pass = all_pass and ok
                rows.append((name, expected_bit, measured_v, "PASS" if ok else "FAIL"))
            # Worst-case digital margin at this corner: the smallest distance
            # any measured node landed from the digital decision threshold --
            # this is the "how close to flipping" continuous quantity that
            # gives a meaningful binding-corner ranking even when every
            # corner passes cleanly (sim/README.md's per-row binding-corner
            # requirement, issue #28).
            margins = [abs(v - digital_threshold_v) for _, _, v, _ in rows if v is not None]
            worst_margin_v = min(margins) if margins else float("nan")
            points.append(dict(
                process_corner=process_corner, temp_c=temp_c, supply_v=supply_v,
                corner_id=cid, rows=rows, all_pass=all_pass,
                worst_margin_v=worst_margin_v, log_text=output,
            ))
            if not quiet:
                print(f"  {cid}: {'PASS' if all_pass else 'FAIL'} (worst digital margin {worst_margin_v:.4f}V)")

    overall_ok = all(p["all_pass"] for p in points)
    binding = min(points, key=lambda p: p["worst_margin_v"])

    if record:
        record_id = evidence.new_record_id()
        # dut_text (not dut_path) below: `dut_path` lived under the
        # TemporaryDirectory `with` block above, which has already been
        # cleaned up by this point -- use the in-memory netlist text
        # (already captured into `dut_text`) via the text-accepting sibling
        # helper instead of re-reading a now-deleted path.
        record_path = evidence.write_netlist_snapshot_text(EXPERIMENT_DIR, record_id, dut_text)
        corners_out_dir = EXPERIMENT_DIR / "corners" / record_id
        corners_out_dir.mkdir(parents=True, exist_ok=True)
        for p in points:
            (corners_out_dir / f"{p['corner_id']}.log").write_text(p["log_text"])

        net_sha = evidence.sha256_text(dut_text)
        process_corners_run = sorted({p["process_corner"] for p in points})
        temps_run = sorted({p["temp_c"] for p in points})
        supplies_run = sorted({p["supply_v"] for p in points})

        lines = [
            f"# Record {record_id}",
            "",
            f"- **Record ID**: {record_id}",
            "- **Claim**: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- "
            "Resolution `N = 10 bit` (RATIFIED, DR-003 via #27): confirms correct "
            "MSB-first bit-by-bit successive-approximation capture of all 10 output "
            "bits, correct clock/phase sequencing, and the ring sequencer's "
            "auto-restart, at every bound corner of the ratified corner set. Distinct "
            "from, and does not supersede, this experiment's prior single-corner "
            "record against `DR-006-sar-sequencer-bit-count-and-timing-budget.md` "
            "(that record's own claim predates ratification and stands unchanged).",
            "- **Netlist provenance**: schematic (`design/sar_sequencer.sch`)",
            corners_mod.corner_matrix_summary_line(
                process_corners_run, temps_run, supplies_run, len(points)
            ),
            "- **Divergence from the shared PVT/MC harness**: this experiment does not run through "
            "`sim/run_corners.py`/`sim/monte_carlo.py` (their shared `.control` block only supports "
            "`.op` analysis; this is a transient/digital sequencing check) -- see "
            "`sim/sar-sequencer-behavioral/run_testbench.py`'s own module docstring.",
            f"- **Stimulus**: ideal comparator-decision (`COMP_OUT`) PWL, two back-to-back "
            f"conversions, CODE1(b9..b0)={''.join(str(b) for b in CODE1)}b, "
            f"CODE2(b9..b0)={''.join(str(b) for b in CODE2)}b, rail-referenced to each "
            "corner's own supply point -- see "
            "`sim/sar-sequencer-behavioral/testbench/sar_sequencer_tb_fragment.spice`.",
            f"- **Binding corner**: `{binding['corner_id']}` (smallest digital margin to the "
            f"decision threshold across all {len(EXPECTED_BITS)} checks: "
            f"{binding['worst_margin_v']:.4f} V) -- recorded regardless of pass/fail, per "
            "sim/README.md's per-row binding-corner convention.",
            f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} "
            f"({sum(1 for p in points if p['all_pass'])}/{len(points)} corners fully correct)",
            "",
            "## Per-corner summary",
            "",
            "| corner-id | all checks correct? | worst digital margin (V) |",
            "|---|---|---|",
        ]
        for p in points:
            lines.append(
                f"| `{p['corner_id']}` | {'PASS' if p['all_pass'] else 'FAIL'} | {p['worst_margin_v']:.4f} |"
            )
        lines.append("")
        lines.append("## Per-check results at the binding corner (`" + binding["corner_id"] + "`)")
        lines.append("")
        lines.append("| check | expected (bit) | measured (V) | pass/fail |")
        lines.append("|---|---|---|---|")
        for name, expected_bit, measured_v, status in binding["rows"]:
            mv = f"{measured_v:.4f}" if measured_v is not None else "MISSING"
            lines.append(f"| `{name}` | {expected_bit} | {mv} | {status} |")
        lines.append("")
        if not overall_ok:
            failing = [p["corner_id"] for p in points if not p["all_pass"]]
            lines.append(
                f"**FAILING corners** ({len(failing)}/{len(points)}): "
                + ", ".join(f"`{c}`" for c in failing)
                + " -- reported as failing, per CLAUDE.md's 'no claim without a "
                "testbench' / 'do not relax a spec line to make a result pass' rules."
            )
            lines.append("")
        lines.extend(
            evidence.environment_block(
                pdk_line=f"{pdk_info.variant} @ {pdk.resolved_commit(pdk_info)}",
                ngspice_line=toolchain._ngspice_version() or "unknown",
                netlist_sha256=net_sha,
            )
        )
        lines.append("")
        lines.extend(evidence.footer_lines("sim/sar-sequencer-behavioral/run_testbench.py --corners", ""))
        record_path.write_text("\n".join(lines))
        print(f"\nRecord written: {record_path.relative_to(REPO_ROOT)}")

    print("OVERALL (all corners): PASS" if overall_ok else "OVERALL (all corners): FAIL")
    return 0 if overall_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin, then exit")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT corner sweep (issue #28) instead of the single nominal point",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.check_env:
        check = toolchain.check_env()
        print(toolchain.summary())
        if check.messages:
            for m in check.messages:
                print(f"FAIL: {m}")
        for w in check.warnings:
            print(f"WARNING: {w}")
        return check.status

    if args.corners:
        return run_corner_campaign(record=args.record, quiet=args.quiet)

    return run(record=args.record)


if __name__ == "__main__":
    raise SystemExit(main())

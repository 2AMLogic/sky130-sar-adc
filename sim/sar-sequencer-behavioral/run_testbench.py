#!/usr/bin/env python3
"""Standalone behavioral testbench runner for design/sar_sequencer.sch
(issue #55).

Cold-start invocation (see docs/environment-setup.md for the one-time
toolchain/PDK bootstrap this assumes):

    source sim/env.sh                                          # export PDK_ROOT / PDK
    python3 sim/sar-sequencer-behavioral/run_testbench.py --check-env
    python3 sim/sar-sequencer-behavioral/run_testbench.py       # run + print PASS/FAIL, no evidence written
    python3 sim/sar-sequencer-behavioral/run_testbench.py --record  # also mint an evidence record

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

from harness import evidence, measure, pdk, toolchain  # noqa: E402

EXPERIMENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = evidence.REPO_ROOT
DESIGN_SCH = REPO_ROOT / "design" / "sar_sequencer.sch"
XSCHEMRC = REPO_ROOT / "sim" / "xschemrc"
FRAGMENT = EXPERIMENT_DIR / "testbench" / "sar_sequencer_tb_fragment.spice"

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
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    out_path = scratch_dir / "sar_sequencer.spice"
    if proc.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"xschem netlisting of {DESIGN_SCH} failed (exit {proc.returncode}):\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return out_path


def assemble_deck(dut_netlist_text: str, pdk_info: pdk.PdkInfo) -> str:
    stdcell_spice = pdk_info.variant_dir / "libs.ref" / "sky130_fd_sc_hd" / "spice" / "sky130_fd_sc_hd.spice"
    if not stdcell_spice.is_file():
        raise RuntimeError(f"sky130_fd_sc_hd combined SPICE deck not found at {stdcell_spice}")

    dut_lines = [ln for ln in dut_netlist_text.splitlines() if ln.strip() != ".end"]
    fragment_text = FRAGMENT.read_text()

    lines = [
        "* sar-sequencer-behavioral -- standalone testbench (issue #55), NOT a",
        "* PVT-corner or Monte-Carlo claim -- see this experiment's own record",
        "* for the divergence from sim/run_corners.py / sim/monte_carlo.py.",
        f".lib {pdk_info.ngspice_lib} tt",
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin, then exit")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
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

    return run(record=args.record)


if __name__ == "__main__":
    raise SystemExit(main())

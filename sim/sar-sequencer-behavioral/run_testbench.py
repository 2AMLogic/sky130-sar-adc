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
    python3 sim/sar-sequencer-behavioral/run_testbench.py --klt-row-evidence --record
        # the same nine-point sweep as ONE `klt sim` request on the batch
        # fleet (issue #1023), whose report is the machine-graded T1 item-5
        # `resolution_n` binding -- see run_row_evidence_campaign()
    python3 sim/sar-sequencer-behavioral/run_testbench.py --probe-klt-row
        # one local single-corner `klt sim` unit (tt/27C/1.8V) validating the
        # request/deck mechanics before any fleet submit; writes no evidence

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
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod, evidence, klt_sim, measure, pdk, toolchain  # noqa: E402

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
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS

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
    stale snapshot. Thin wrapper around toolchain.netlist_with_xschem()
    (issue #205): shares its timeout budget with toolchain.run_ngspice()'s
    own ngspice invocations (issue #133) rather than a second hardcoded
    literal here, so SIM_NGSPICE_TIMEOUT_S raises both this step's and the
    .tran run's budget together on a slower-but-still-progressing host."""
    return toolchain.netlist_with_xschem(
        DESIGN_SCH, scratch_dir, XSCHEMRC, "sar_sequencer.spice"
    )


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


def run(record: bool, supersedes: str = "") -> int:
    gate = toolchain.preflight()
    if gate is not None:
        return gate

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
            prov = evidence.resolve_provenance(EXPERIMENT_DIR, dut_text)
            record_id = prov.record_id
            runs_dir = EXPERIMENT_DIR / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)
            (runs_dir / f"{record_id}.log").write_text(output)

            net_sha = prov.netlist_sha
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
                    pdk_line=prov.pdk_line,
                    ngspice_line=prov.ng_version,
                    netlist_sha256=net_sha,
                )
            )
            lines.append("")
            lines.extend(evidence.footer_lines(
                "sim/sar-sequencer-behavioral/run_testbench.py", supersedes
            ))
            evidence.close_record(prov, lines, "Record")
            evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)

        return 0 if all_pass else 1


def run_corner_campaign(
    record: bool, quiet: bool = False, supersedes: str = ""
) -> int:
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
    gate = toolchain.preflight()
    if gate is not None:
        return gate

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
        # dut_text (not dut_path) below: `dut_path` lived under the
        # TemporaryDirectory `with` block above, which has already been
        # cleaned up by this point -- use the in-memory netlist text
        # (already captured into `dut_text`) via resolve_provenance()'s
        # text-accepting snapshot helper instead of re-reading a now-deleted
        # path.
        prov = evidence.resolve_provenance(EXPERIMENT_DIR, dut_text)
        record_id = prov.record_id
        corners_out_dir = EXPERIMENT_DIR / "corners" / record_id
        corners_out_dir.mkdir(parents=True, exist_ok=True)
        for p in points:
            (corners_out_dir / f"{p['corner_id']}.log").write_text(p["log_text"])

        net_sha = prov.netlist_sha
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
                pdk_line=prov.pdk_line,
                ngspice_line=prov.ng_version,
                netlist_sha256=net_sha,
            )
        )
        lines.append("")
        lines.extend(evidence.footer_lines(
            "sim/sar-sequencer-behavioral/run_testbench.py --corners", supersedes
        ))
        evidence.close_record(prov, lines, "Record")
        evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)

    print("OVERALL (all corners): PASS" if overall_ok else "OVERALL (all corners): FAIL")
    return 0 if overall_ok else 1


# --------------------------------------------------------------------------- #
# Issue #1023: the same nine-point sweep as ONE `klt sim` request, whose
# report is the machine-graded T1 item-5 `resolution_n` binding.
#
# The August corner record above is this campaign's own reference method: a
# locally assembled deck per corner, margins graded in Python against
# EXPECTED_BITS. A `klt signoff` item-5 citation, however, accepts a `klt
# sim` envelope, and derived row coverage (klayout-tools#3778) credits a row
# only from a PASSING, limits-bearing measurement tagged with
# `measurements[].spec_row` -- so the row needs the check set expressed as
# request measurements, not as a prose table.
#
# The pass/fail quantity is the runner's own decision quantity: the SIGNED
# margin of each sampled node about half the rail, `v(node) -
# 0.5*v(VPWR)`. The manual runner computes that comparison in Python
# (`1 if measured_v > 0.5*supply_v else 0`, the `digital_threshold_v` of
# run()/run_corner_campaign()); a `klt sim` limit is a static number, so the
# comparison is moved INTO the deck as one testbench-only behavioural source
# per measured node (`Bm_<node>`) and each `.meas` card samples that
# source's node instead of the raw one. Because the helper references the
# rail NODE, the margin is rail-referenced at every supply the corner axis
# sets -- the limit `min: 0` (expected 1) / `max: 0` (expected 0) then
# expresses exactly "above half the rail at this corner's own supply". The
# one semantic delta vs the Python rule is the boundary itself: a limit is
# inclusive, the runner's comparison is strict, so a sample landing exactly
# ON half rail would pass the limit while the runner reads it as 0. No
# sample of the August record came within 0.80 V of that boundary (its
# binding margin is 0.8099 V), the same nodes at the same corners.
# --------------------------------------------------------------------------- #

#: The spec row this run grades -- the SAME id the manifest declares under
#: `spec_rows["5.digital"]` and the citation names under `rows`, per the
#: issue's "use `resolution_n` consistently" rule.
SPEC_ROW_ID = "resolution_n"

#: `models` of the `klt sim` request: the PDK-relative spelling every other
#: klt campaign in this repo uses, resolved by the executing worker against
#: its own PDK_ROOT.
KLT_MODELS = {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"}

#: The standard-cell subcircuit deck the DUT's `sky130_fd_sc_hd__*`
#: instances resolve to. `$PDK_ROOT` is expanded by `klt sim` on the box
#: that runs the deck (the same spelling sim/digital-partition/ and
#: sim/reference-drive-budget/ use), never this host's absolute path.
STDCELL_INCLUDE = "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"

#: The fragment's own supply parameter, swept as the `corners.params` axis
#: (every source card in the fragment is an expression in `{vdd_val}`, and
#: `corners.supply_v` `alter`s a source INSTANCE -- klt refuses it for a
#: PWL/PULSE source anyway -- so the parameter axis is the only form that
#: moves the rail and the rail-referenced stimulus together; the same
#: choice sim/reference-drive-budget/ documents for the same reason).
VDD_PARAM = "vdd_val"

#: Suffix naming each margin helper's output node (`<node>_hf` -- the
#: half-rail margin of `<node>`).
MARGIN_SUFFIX = "_hf"

#: Per-unit `klt sim` kill. Generous by design: the same deck solves in
#: seconds locally, and a timeout is a lost unit, not a retry.
KLT_ROW_TIMEOUT_S = 1800.0

#: One `.meas` card of the committed fragment: `<name> find v(<node>) at=<t>`
#: (xschem-era spelling, lowercase keywords, exactly the form every record
#: of this campaign since August has graded against).
_MEAS_RE = re.compile(
    r"^\.meas\s+tran\s+(\w+)\s+find\s+v\((\w+)\)\s+at\s*=\s*(\S+)\s*$",
    re.IGNORECASE,
)


def parse_meas_cards(meas_cards: list[str]) -> list[tuple[str, str, str, str]]:
    """The committed fragment's `.meas` cards (already separated, and already
    checked against EXPECTED_BITS' key set, by `klt_sim.split_fragment`) as
    `(name, node, at, card)` tuples. A card that is not the
    `find v(<node>) at=<t>` form fails here instead of silently producing a
    request that measures something else."""
    out = []
    for card in meas_cards:
        match = _MEAS_RE.match(card.strip())
        if match is None:
            raise RuntimeError(
                f"unparsed .meas card in the committed fragment: {card!r} -- "
                "the fragment changed shape; re-derive this campaign."
            )
        out.append((match.group(1), match.group(2), match.group(3), card.strip()))
    return out


def split_row_fragment(fragment_text: str) -> tuple[str, list[tuple[str, str, str, str]], str]:
    """Split the committed fragment into the circuit BODY (sources only --
    `klt sim` owns the `.control`/`.end` wrapper), the parsed `.meas`
    checks, and the `.tran` card's arguments (`analysis.args`). The split and
    its shape assertions are the shared harness helper's; only the `.meas`
    card parsing is this campaign's."""
    body, meas_cards, tran_args = klt_sim.split_fragment(fragment_text, list(EXPECTED_BITS))
    return body, parse_meas_cards(meas_cards), tran_args


def margin_helper_lines(meas: list[tuple[str, str, str, str]]) -> list[str]:
    """The testbench-only behavioural margin sources, one per measured node.

    `Bm_<node> <node>_hf 0 V = v(<node>) - 0.5*v(VPWR)` -- a measurement
    helper, not a DUT or stimulus change: it loads nothing (a B-source's
    output is driven), and every `.meas` card below samples `<node>_hf`
    instead of `<node>` so the request's static limits express the runner's
    rail-referenced decision rule at every supply the corner axis sets."""
    lines = [
        "* --- testbench-only half-rail margin helpers (issue #1023; NOT DUT",
        "* devices): each node's signed distance from half the rail, so a",
        "* static `klt sim` limit can express `sample > half the rail at this",
        "* corner's own supply` as `margin > 0`. The runner's Python rule this",
        "* mirrors is run_corner_campaign()'s digital_threshold_v comparison.",
    ]
    for node in sorted({node for _, node, _, _ in meas}):
        lines.append(
            f"Bm_{node} {node}{MARGIN_SUFFIX} 0 V = v({node}) - 0.5*v(VPWR)"
        )
    return lines


def margin_measurement_entries(meas: list[tuple[str, str, str, str]]) -> list[dict]:
    """One `measurements[]` entry per committed check: the fragment's own
    `.meas` card with the sampled node re-pointed at its margin helper,
    `unit: V`, the row tag, and the limit EXPECTED_BITS decides.

    Expected 1 -> `{"min": 0}` (the sample must sit above half the rail);
    expected 0 -> `{"max": 0}`. `klt sim` requires the card's measurement
    name to equal the entry name, which the rewrite preserves."""
    entries = []
    for name, node, _at, card in meas:
        rewritten = re.sub(
            rf"v\({re.escape(node)}\)",
            f"v({node}{MARGIN_SUFFIX})",
            card,
            count=1,
        )
        if rewritten == card:
            raise RuntimeError(f"failed to re-point .meas card at its margin node: {card!r}")
        limits = {"min": 0.0} if EXPECTED_BITS[name] == 1 else {"max": 0.0}
        entries.append(
            {
                "name": name,
                "spice": rewritten,
                "unit": "V",
                "spec_row": SPEC_ROW_ID,
                "limits": limits,
            }
        )
    return entries


def row_saved_vectors(meas: list[tuple[str, str, str, str]]) -> list[str]:
    """Exactly the vectors the re-pointed `.meas` cards read, so no unit
    carries a `save all` rawfile (the same economy
    sim/reference-drive-budget/ applies)."""
    nodes = {node for _, node, _, _ in meas}
    return sorted(f"v({node}{MARGIN_SUFFIX})" for node in nodes)


def row_exclude(points: list[tuple[str, float, float]]) -> list[dict]:
    """The `exclude` rules that reduce the crossed axes' full product to
    exactly `points` (the nine-point OAT star, or the probe's single point).

    One full-spec rule per crossed point the star does not contain --
    generated, never hand-listed, so the rule set cannot drift from the
    grid. Each rule names all three axes, so it drops exactly one point."""
    procs = sorted({p for p, _, _ in points})
    temps = sorted({t for _, t, _ in points})
    vdds = sorted({v for _, _, v in points})
    want = set(points)
    return [
        {"process": p, "temperature_c": t, "params": {VDD_PARAM: v}}
        for p in procs
        for t in temps
        for v in vdds
        if (p, t, v) not in want
    ]


def build_row_request(
    netlist_name: str,
    tran_args: str,
    meas: list[tuple[str, str, str, str]],
    points: list[tuple[str, float, float]],
    *,
    timeout_s: float = KLT_ROW_TIMEOUT_S,
) -> dict:
    """The ONE `klt sim` request covering exactly `points`."""
    procs = sorted({p for p, _, _ in points})
    temps = sorted({t for _, t, _ in points})
    vdds = sorted({v for _, _, v in points})
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": dict(KLT_MODELS),
        "corners": {
            "process": procs,
            "temperature_c": temps,
            "params": {VDD_PARAM: vdds},
        },
        "analysis": {"kind": "tran", "args": tran_args},
        "measurements": margin_measurement_entries(meas),
        "options": {
            "timeout_s": timeout_s,
            "keep_artifacts": True,
            "save_vectors": row_saved_vectors(meas),
            "ngspice_init": ["set numdgt=10"],
        },
    }
    exclude = row_exclude(points)
    if exclude:
        req["exclude"] = exclude
    return req


def build_row_body(dut_text: str, fragment_text: str) -> str:
    """The circuit BODY `klt sim` wraps: no `.lib`, no `.temp`, no `.meas`,
    no `.tran`, no `.control`, no `.end` (docs/cli/sim.md, "Netlist
    convention"). The corner's `.lib`/`.temp` cards, the analysis and the
    `.meas` cards all come from the request; `vdd_val` is declared here
    because `corners.params` addresses an existing top-level `.param`.

    The DUT section is the freshly `klt netlist`ed schematic with only its
    `.end` and its two checkout-path-bearing `**`-comment header lines
    removed -- device content byte-identical, and the inert `**.subckt`
    wrapper line left exactly as xschem writes it (every record of this
    campaign since August graded that same flat form; see the record's
    divergence notes). The fragment's source cards are used verbatim,
    `{vdd_val}` expressions intact, so the parameter axis moves rail and
    rail-referenced stimulus together exactly as the per-corner deck
    rewrite always did."""
    frag_body, meas, _tran = split_row_fragment(fragment_text)
    dut_lines = [
        ln
        for ln in dut_text.splitlines()
        if ln.strip().lower() != ".end"
        and not ln.startswith("** sch_path:")
        and not ln.startswith("** klt-netlist-inputs:")
    ]
    lines = [
        "* sim/sar-sequencer-behavioral -- `klt sim` row-evidence deck body",
        "* (issue #1023). Assembled by",
        "* sim/sar-sequencer-behavioral/run_testbench.py --klt-row-evidence.",
        "* Circuit body only: klt sim supplies the .lib corner section, .temp,",
        "* the .meas cards, the .tran analysis and the .control wrapper. The DUT",
        "* and stimulus are this campaign's own (design/sar_sequencer.sch",
        "* netlisted fresh; testbench/sar_sequencer_tb_fragment.spice devices",
        "* verbatim), plus the margin helpers named below.",
        "* One solver thread per unit: concurrent units on a shared runner must",
        "* not oversubscribe it (the same card sim/digital-partition/ carries).",
        ".options num_threads=1",
        f".param {VDD_PARAM} = {NOMINAL_SUPPLY_V:g}",
        f".include {STDCELL_INCLUDE}",
        "",
        *dut_lines,
        "",
        frag_body.rstrip("\n"),
        "",
        *margin_helper_lines(meas),
    ]
    return "\n".join(lines) + "\n"


def netlist_dut_klt(scratch_dir: Path, runner=klt_sim.default_runner) -> str:
    """Netlist design/sar_sequencer.sch with `klt netlist` (never raw xschem
    -- CLAUDE.md's host rule: a bare xschem can hang in its Tk loop) and
    return the normalized DUT text the deck body embeds.

    `klt netlist` owns the xschem invocation: headless flags always passed,
    a real timeout with SIGTERM->SIGKILL escalation, success judged by the
    output file existing. The text is normalized exactly as build_row_body()
    documents: `.end` and the two checkout-path-bearing header comments
    dropped, everything else byte-identical, so the committed deck body and
    its hash are independent of which checkout produced them."""
    out_path = scratch_dir / "sar_sequencer.spice"
    argv = [
        "klt", "netlist", str(DESIGN_SCH),
        "-o", str(out_path),
        "--rcfile", str(XSCHEMRC),
    ]
    rc, out, err = runner(argv)
    if rc != 0 or not out_path.is_file():
        raise RuntimeError(
            f"klt netlist of {DESIGN_SCH} failed (rc={rc}):\n{klt_sim.error_excerpt(err or out)}"
        )
    text = out_path.read_text()
    normalized = "\n".join(
        ln
        for ln in text.splitlines()
        if ln.strip().lower() != ".end"
        and not ln.startswith("** sch_path:")
        and not ln.startswith("** klt-netlist-inputs:")
    ) + "\n"
    return normalized


def decode_row_report(report: dict) -> tuple[list[dict], bool]:
    """Decode a row-evidence report into per-corner points.

    Each point carries the repo-style corner id (`tt_27c_1.62v`, the same
    spelling every record of this campaign uses), the corner's supply (from
    its `params` row -- the axis this request sweeps), and per-check rows
    `(name, expected_bit, margin_v, raw_v, ok)` with the runner's own bit
    rule (`margin > 0` -> 1, else 0) applied so the record's PASS/FAIL is
    decided exactly as run_corner_campaign() decides it. The supply must be
    explicit in each corner's params (never assumed nominal). A corner whose
    own status is a limit failure keeps its finite readings; a reading that
    is absent or non-finite is reported missing, never zero."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {json.dumps(report['error'])}")
    points = []
    overall_ok = True
    for corner in report.get("corners") or []:
        params = corner.get("params") or {}
        if VDD_PARAM not in params or not klt_sim.finite(params[VDD_PARAM]):
            raise ValueError(
                f"corner {corner.get('corner_id')!r} carries no explicit "
                f"`{VDD_PARAM}` supply in its params -- refusing to assume nominal"
            )
        supply_v = float(params[VDD_PARAM])
        cid = corners_mod.corner_id(corner["process"], float(corner["temperature_c"]), supply_v)
        rows = []
        all_pass = corner.get("status") == "pass"
        # Readings are kept for every corner that reported them, including a
        # corner whose own status is a limit failure: the values are the
        # diagnostic. Only a missing / non-finite reading is reported MISSING.
        values = {
            m["name"]: m.get("value")
            for m in (corner.get("measurements") or [])
            if isinstance(m, dict) and "name" in m
        }
        for name in sorted(EXPECTED_BITS):
            expected_bit = EXPECTED_BITS[name]
            margin_v = values.get(name)
            if margin_v is None or not klt_sim.finite(margin_v):
                all_pass = False
                rows.append((name, expected_bit, None, None, False))
                continue
            measured_bit = 1 if margin_v > 0.0 else 0
            raw_v = margin_v + 0.5 * supply_v
            ok = measured_bit == expected_bit
            all_pass = all_pass and ok
            rows.append((name, expected_bit, margin_v, raw_v, ok))
        overall_ok = overall_ok and all_pass
        margins = [abs(m) for _, _, m, _, _ in rows if m is not None]
        points.append(
            {
                "corner_id": cid,
                "klt_corner_id": corner.get("corner_id"),
                "process_corner": corner["process"],
                "temp_c": float(corner["temperature_c"]),
                "supply_v": supply_v,
                "rows": rows,
                "all_pass": all_pass,
                "worst_margin_v": min(margins) if margins else float("nan"),
            }
        )
    return points, overall_ok


def check_corner_identities(points: list[dict], requested) -> str | None:
    """None when `points` holds exactly one result per requested
    (process, temperature_c, supply_v) tuple; otherwise a one-line reason.
    Guards against a count-only check passing a report that duplicates one
    corner and omits another."""
    want = sorted(
        corners_mod.corner_id(p, float(t), float(v)) for p, t, v in requested
    )
    got = sorted(p["corner_id"] for p in points)
    if got == want:
        return None
    dupes = sorted({c for c in got if got.count(c) > 1})
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    return (
        f"report corners do not match the request (duplicated: {dupes or 'none'}; "
        f"missing: {missing or 'none'}; unrequested: {extra or 'none'})"
    )


def binding_point(points: list[dict]) -> dict | None:
    """The point with the smallest finite worst margin, or None when no
    point carries a finite margin."""
    finite_pts = [p for p in points if p["worst_margin_v"] == p["worst_margin_v"]]
    return min(finite_pts, key=lambda p: p["worst_margin_v"]) if finite_pts else None


def failing_checks(points: list[dict]) -> list[str]:
    """One `corner / check / value` line per failing check."""
    out = []
    for p in points:
        for name, expected_bit, margin_v, raw_v, ok in p["rows"]:
            if ok:
                continue
            val = f"margin {margin_v:.4f} V" if margin_v is not None else "no finite reading"
            out.append(f"`{p['corner_id']}` / `{name}` (expected {expected_bit}): {val}")
    return out


def worker_environment(report: dict, prov) -> tuple[str, str, list[str]]:
    """(pdk_line, ngspice_line, extra_lines): the canonical Environment
    values come from the executing worker's own evidence; the submitting
    host's values are kept separately labelled, and a fallback to the host
    is stated."""
    info = klt_sim.run_info(report)
    pdk = info["worker_pdk"]
    ng = info["worker_ngspice"]
    notes = []
    if not pdk:
        notes.append(
            f"PDK: no single executing-worker value reported (seen: {info['worker_pdks_seen'] or 'none'}); "
            f"FALLBACK to the submitting host's {prov.pdk_line}"
        )
    if not ng:
        notes.append(
            f"ngspice: no single executing-worker value reported (seen: {info['worker_ngspice_seen'] or 'none'}); "
            f"FALLBACK to the submitting host's {prov.ng_version}"
        )
    return pdk or prov.pdk_line, ng or prov.ng_version, notes


def attributed_environment_lines(
    env_pdk: str, env_ng: str, env_notes: list[str]
) -> tuple[str, str]:
    """The Environment block's `- PDK:` / `- ngspice:` lines from
    `worker_environment()`'s values and notes: `(executing worker)` only on
    a value the worker reported, and a field that fell back keeps the
    submitting host's value under a label saying so. Decided per field, on
    that field's own note (`PDK: ...` / `ngspice: ...`), because the fallback
    is per field -- never by comparing against the host's value, which a
    worker is free to agree with (issue #1096)."""
    pdk_fell_back = any(note.startswith("PDK:") for note in env_notes)
    ng_fell_back = any(note.startswith("ngspice:") for note in env_notes)
    fell_back_label = " (submitting host; no single executing-worker value reported)"
    return (
        env_pdk + (fell_back_label if pdk_fell_back else " (executing worker)"),
        env_ng + (fell_back_label if ng_fell_back else " (executing worker)"),
    )


def _copy_corner_logs(report: dict, corners_dir: Path) -> list[str]:
    """Copy each unit's ngspice log out of the (scratch) artifacts dir into
    `corners_dir` as committed raw evidence, returning the basenames."""
    copied = []
    for corner in report.get("corners") or []:
        log = ((corner.get("artifacts") or {}).get("log")) or ""
        if not log:
            continue
        source = Path(log)
        if not source.is_file():
            continue
        target = corners_dir / f"{corner.get('slug') or source.parent.name}.ngspice.log"
        if not target.exists():
            target.write_bytes(source.read_bytes())
        copied.append(target.name)
    return sorted(copied)


def _klt_run_lines(report: dict, request_rel: str, report_rel: str) -> list[str]:
    """The record's `## klt sim run` block: the batch job, the executing
    PDK/simulator, and where the committed request/report live."""
    info = klt_sim.run_info(report)
    lines = ["## `klt sim` run", ""]
    for job in info["jobs"] or [{}]:
        lines.append(
            f"- job `{job.get('job_id')}`, status `{info['status']}`, backend "
            f"`{info['resolved_backend']}`, executing PDK `{info['worker_pdk']}`, "
            f"executing simulator `{info['worker_ngspice']}`"
        )
        lines.append(
            f"- job `{job.get('job_id')}`: state `{job.get('state')}`, exit "
            f"`{job.get('exit_code')}`, runner klt `{job.get('runner_klt_version')}`, "
            f"client klt `{job.get('client_klt_version')}` "
            f"(`{job.get('runner_compatibility')}`)"
        )
    lines.append(
        f"- request and deck body: `{request_rel}`; raw report: `{report_rel}`"
    )
    return lines


#: Deck divergences from the per-corner reference method, stated once here
#: and rendered into every record this mode mints.
ROW_PORT_NOTES = [
    (
        "Margin helper sources",
        "each measured node gets a testbench-only behavioural source "
        "`Bm_<node>` whose output is the node's signed distance from half "
        "the rail (`v(node) - 0.5*v(VPWR)`), and each `.meas` card samples "
        "that helper's node. A `klt sim` limit is a static number, so this "
        "is how the request expresses the runner's actual decision rule "
        "(a sample above half the RAIL -- 0.81/0.90/0.99 V across the axis "
        "-- is a one) instead of a fixed volt threshold. The helpers drive "
        "nothing and load nothing; the DUT and stimulus are unmodified."
    ),
    (
        "Supply as a parameter axis",
        "the per-corner deck rewrite set `.param vdd_val = <supply>` per "
        "point; the shared body declares `.param vdd_val = 1.8` and "
        "`corners.params` sets it per corner via `alterparam` + `reset`, "
        "which re-evaluates every `{vdd_val}` expression (rail source and "
        "the rail-referenced CLK/RST_B/COMP_OUT stimulus together). "
        "`corners.supply_v` cannot be used here: it `alter`s a source "
        "instance, and klt refuses that for a PWL/PULSE source."
    ),
    (
        "Standard-cell library include",
        "`$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/spice/"
        "sky130_fd_sc_hd.spice`, expanded by the executing worker against "
        "its own PDK_ROOT (the same spelling sim/digital-partition/ uses), "
        "in place of the per-corner deck's absolute path into this "
        "checkout's PDK."
    ),
    (
        "Netlisting via `klt netlist`",
        "the DUT is netlisted with `klt netlist` (which owns the xschem "
        "invocation, its headless flags and its timeout) instead of the "
        "harness's direct xschem call. Only `.end` and the two "
        "checkout-path-bearing `**`-comment header lines are dropped from "
        "the embedded text; device content is byte-identical, and the "
        "inert `**.subckt` wrapper comment xschem writes is left in place "
        "-- every record of this campaign since August graded that same "
        "flat form."
    ),
    (
        "Deck mechanics owned by the request",
        "`.options num_threads=1` (one solver thread per unit), the `.tran` "
        "arguments, and the `.meas` cards moved from the fragment into the "
        "request's `analysis`/`measurements` fields -- `klt sim` owns the "
        "`.control` wrapper. The fragment's device cards are used verbatim."
    ),
]


def run_row_evidence_campaign(
    record: bool, backend: str | None = None, quiet: bool = False, supersedes: str = ""
) -> int:
    """The nine-point OAT sweep as ONE `klt sim` request (issue #1023).

    Same DUT, same committed fragment, same 35 named checks and same
    nine ratified PVT points as run_corner_campaign() -- different
    execution: the grid goes to the batch fleet as a single `klt sim`
    request through sim/harness/klt_sim.py (which passes
    `--wait-for-capacity 600` on every non-local submit), and the pass/fail
    quantity is the margin helper each check samples, graded by `klt sim`
    against the limits the request declares. The committed report's
    `measurements[].spec_row` tags are what `klt signoff` derives the
    `resolution_n` row's coverage from; this campaign is that row's
    machine-graded binding, a SEPARATE claim from #811's
    baseline-agreement and supersession work -- it supersedes no record."""
    gate = toolchain.preflight()
    if gate is not None:
        return gate

    with tempfile.TemporaryDirectory(prefix="sar-sequencer-klt-") as scratch:
        scratch_dir = Path(scratch)
        dut_text = netlist_dut_klt(scratch_dir)
        fragment_text = FRAGMENT.read_text()
        body = build_row_body(dut_text, fragment_text)
        _frag_body, meas, tran_args = split_row_fragment(fragment_text)

        grid = corners_mod.ratified_oat_grid(
            NOMINAL_SUPPLY_V, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )
        request = build_row_request("tb.spice", tran_args, meas, grid)

        prov = evidence.resolve_provenance(EXPERIMENT_DIR, dut_text)
        record_id = prov.record_id
        corners_dir = EXPERIMENT_DIR / "corners" / record_id
        request_dir = corners_dir / "request"
        request_dir.mkdir(parents=True, exist_ok=True)
        (request_dir / "tb.spice").write_text(body)
        (request_dir / "request.json").write_text(json.dumps(request, indent=1) + "\n")

        report = klt_sim.submit(
            request_dir / "request.json",
            scratch_dir / "out",
            backend=backend,
            label="sar-sequencer-behavioral row evidence",
            report_path=corners_dir / "report.json",
        )
        logs = _copy_corner_logs(report, corners_dir)

    points, overall_ok = decode_row_report(report)
    mismatch = check_corner_identities(points, grid)
    if mismatch is not None:
        print(f"FAIL: {mismatch} -- refusing to grade a mismatched grid.")
        return 1
    binding = binding_point(points)
    if binding is None:
        print("FAIL: no corner carries a finite margin -- nothing to grade.")
        overall_ok = False

    for p in points:
        if not quiet:
            print(
                f"  {p['corner_id']}: {'PASS' if p['all_pass'] else 'FAIL'} "
                f"(worst digital margin {p['worst_margin_v']:.4f}V)"
            )

    if record:
        request_rel = f"corners/{record_id}/request"
        report_rel = f"corners/{record_id}/report.json"
        net_sha = prov.netlist_sha
        lines = [
            f"# Record {record_id}",
            "",
            f"- **Record ID**: {record_id}",
            "- **Claim**: `spec/target-spec.md#numeric-rows--ratified-2026-08-19` -- "
            "Resolution `N = 10 bit` (RATIFIED, DR-003 via #27), machine-graded "
            "binding for the digital partition's T1 item-5 row set (issue #1023): "
            "correct MSB-first bit-by-bit successive-approximation capture of all "
            "10 output bits, correct clock/phase sequencing, and the ring "
            "sequencer's auto-restart, at every bound corner of the ratified "
            "corner set, expressed as `klt sim` measurements tagged "
            f"`{SPEC_ROW_ID}` with limits, so `klt signoff` derives the row's "
            "coverage from the envelope instead of a manifest assertion. Same "
            "DUT (the revised sequencer with `COMP_EFF` and per-conversion "
            "gating), same fragment, same 35 named checks and same nine PVT "
            "points as the September corner record "
            "(`records/20260912-004028-9aaf1ca.md`); the August record "
            "(`records/20260827-211956-e13bc1e.md`) graded an earlier DUT and "
            "fragment and shares only the checks, expected codes and grid; a "
            "SEPARATE claim from "
            "#811's baseline-agreement and supersession work -- this record "
            "supersedes nothing and states nothing about #811's agreement gate.",
            "- **Netlist provenance**: schematic (`design/sar_sequencer.sch`), "
            "netlisted fresh with `klt netlist` (see the divergence notes below)",
            corners_mod.corner_matrix_summary_line(
                sorted({p["process_corner"] for p in points}),
                sorted({p["temp_c"] for p in points}),
                sorted({p["supply_v"] for p in points}),
                len(points),
            ),
            "- **Divergence from the shared PVT/MC harness**: same as every "
            "record of this campaign (a transient/digital sequencing check the "
            "`.op`-only shared `.control` block cannot express) -- and, new "
            "here, the grid is ONE `klt sim` request on the batch fleet, not a "
            "local ngspice loop (CLAUDE.md's host rule).",
            f"- **Stimulus**: unchanged `testbench/sar_sequencer_tb_fragment.spice` "
            f"device cards, ideal comparator-decision (`COMP_OUT`) PWL, two "
            f"back-to-back conversions, CODE1(b9..b0)={''.join(str(b) for b in CODE1)}b, "
            f"CODE2(b9..b0)={''.join(str(b) for b in CODE2)}b, rail-referenced to each "
            "corner's own supply point through the fragment's own `{vdd_val}` "
            "expressions.",
            "- **Decision rule**: the runner's own -- a sample above half the "
            "rail at that corner's supply is a one, otherwise zero. Each check "
            "measures its node's signed margin about half the rail (a "
            "testbench-only helper source; see the divergence notes) and the "
            "request grades `margin > 0` (expected 1) / `margin < 0` "
            "(expected 0). The limit is inclusive at exactly zero and the "
            "runner's comparison is strict; "
            + (
                f"no sample in this run sat within {binding['worst_margin_v']:.4f} V "
                "of that boundary."
                if binding is not None and overall_ok
                else "see the failing-check list for any sample that missed its limit."
            ),
            (
                f"- **Binding corner**: `{binding['corner_id']}` (smallest finite "
                f"digital margin to the decision threshold across all "
                f"{len(EXPECTED_BITS)} checks: {binding['worst_margin_v']:.4f} V) -- "
                "recorded regardless of pass/fail, per sim/README.md's per-row "
                "binding-corner convention."
                if binding is not None
                else "- **Binding corner**: NONE -- no corner carried a finite "
                "margin, so no binding point can be named."
            ),
            f"- **Overall**: {'PASS' if overall_ok else 'FAIL'} "
            f"({sum(1 for p in points if p['all_pass'])}/{len(points)} corners "
            "fully correct)",
            "",
            "## Per-corner summary",
            "",
            "| corner-id | all checks correct? | worst digital margin (V) |",
            "|---|---|---|",
        ]
        for p in points:
            lines.append(
                f"| `{p['corner_id']}` | {'PASS' if p['all_pass'] else 'FAIL'} "
                f"| {p['worst_margin_v']:.4f} |"
            )
        if binding is not None:
            lines += [
                "",
                "## Per-check results at the binding corner (`" + binding["corner_id"] + "`)",
                "",
                "| check | expected (bit) | measured (V) | margin to half-rail (V) | pass/fail |",
                "|---|---|---|---|---|",
            ]
            for name, expected_bit, margin_v, raw_v, status in binding["rows"]:
                mv = f"{margin_v:.4f}" if margin_v is not None else "MISSING"
                rv = f"{raw_v:.4f}" if raw_v is not None else "MISSING"
                lines.append(
                    f"| `{name}` | {expected_bit} | {rv} | {mv} | "
                    f"{'PASS' if status else 'FAIL'} |"
                )
        fails = failing_checks(points)
        if fails:
            lines += ["", "## Failing checks (corner / check / value)", ""]
            lines += [f"- {f}" for f in fails]
        if logs:
            lines += [
                "",
                "## Raw per-corner ngspice logs",
                "",
                *(
                    f"- `corners/{record_id}/{name}`"
                    for name in logs
                ),
            ]
        lines += ["", "## `klt sim` run", ""]
        lines += _klt_run_lines(report, request_rel, report_rel)[2:]
        lines += [
            "",
            "## Deck divergences from the per-corner reference method",
            "",
            "Each is a consequence of one shared deck body with the corner "
            "applied as an axis, not a change of mechanism:",
            "",
        ]
        for title, note in ROW_PORT_NOTES:
            lines.append(f"- **{title}.** {note}")
        if not overall_ok:
            failing = [p["corner_id"] for p in points if not p["all_pass"]]
            lines += [
                "",
                f"**FAILING corners** ({len(failing)}/{len(points)}): "
                + ", ".join(f"`{c}`" for c in failing)
                + " -- reported as failing, per CLAUDE.md's 'no claim without a "
                "testbench' / 'do not relax a spec line to make a result pass' rules.",
            ]
        lines.append("")
        env_pdk, env_ng, env_notes = worker_environment(report, prov)
        pdk_line, ngspice_line = attributed_environment_lines(env_pdk, env_ng, env_notes)
        lines.extend(
            evidence.environment_block(
                pdk_line=pdk_line,
                ngspice_line=ngspice_line,
                netlist_sha256=net_sha,
                extra={
                    "klt (client)": report.get("provenance", {}).get("klt_version", "unknown"),
                    "klt (fleet runner)": (
                        (klt_sim.run_info(report)["jobs"] or [{}])[0].get(
                            "runner_klt_version"
                        )
                        or "unknown"
                    ),
                    "Submitting host (not the executor)": (
                        f"{prov.pdk_line} / {prov.ng_version}"
                    ),
                    **({"Environment fallback": "; ".join(env_notes)} if env_notes else {}),
                },
            )
        )
        lines.append("")
        lines.extend(evidence.footer_lines(
            "sim/sar-sequencer-behavioral/run_testbench.py --klt-row-evidence --record",
            supersedes,
        ))
        evidence.close_record(prov, lines, "Record")
        evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)

    print(
        "OVERALL (klt row evidence, all corners): PASS"
        if overall_ok
        else "OVERALL (klt row evidence, all corners): FAIL"
    )
    return 0 if overall_ok else 1


def run_row_probe() -> int:
    """One local single-corner `klt sim` unit (tt/27C/1.8V): validates the
    deck body and request mechanics against the same simulator before any
    fleet submit, prints the 35 margins with the runner's bit rule applied,
    and writes no evidence. The sanctioned local exception to the
    batch-fleet rule -- ONE unit, one corner."""
    gate = toolchain.preflight()
    if gate is not None:
        return gate

    with tempfile.TemporaryDirectory(prefix="sar-sequencer-probe-") as scratch:
        scratch_dir = Path(scratch)
        dut_text = netlist_dut_klt(scratch_dir)
        fragment_text = FRAGMENT.read_text()
        body = build_row_body(dut_text, fragment_text)
        _frag_body, meas, tran_args = split_row_fragment(fragment_text)
        request = build_row_request(
            "tb.spice", tran_args, meas, [("tt", 27.0, NOMINAL_SUPPLY_V)]
        )
        request.pop("exclude", None)
        workdir = scratch_dir / "request"
        workdir.mkdir()
        (workdir / "tb.spice").write_text(body)
        (workdir / "request.json").write_text(json.dumps(request, indent=1) + "\n")
        report = klt_sim.submit(
            workdir / "request.json",
            scratch_dir / "out",
            backend="local",
            label="sar-sequencer-behavioral row probe",
        )

    points, overall_ok = decode_row_report(report)
    mismatch = check_corner_identities(points, [("tt", 27.0, NOMINAL_SUPPLY_V)])
    if mismatch is not None:
        print(f"FAIL: {mismatch}")
        return 1
    for p in points:
        print(
            f"  {p['corner_id']} (klt `{p['klt_corner_id']}`): "
            f"{'PASS' if p['all_pass'] else 'FAIL'} "
            f"(worst digital margin {p['worst_margin_v']:.4f}V)"
        )
    print("OVERALL (local probe): PASS" if overall_ok else "OVERALL (local probe): FAIL")
    return 0 if overall_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-env", action="store_true", help="only check toolchain/PDK pin, then exit")
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT corner sweep (issue #28) instead of the single nominal point",
    )
    ap.add_argument(
        "--klt-row-evidence", action="store_true",
        help="run the nine-point sweep as ONE `klt sim` request on the batch "
        "fleet (issue #1023), producing the machine-graded `resolution_n` "
        "row binding",
    )
    ap.add_argument(
        "--probe-klt-row", action="store_true",
        help="one local single-corner `klt sim` unit validating the row-evidence "
        "deck/request mechanics; writes no evidence",
    )
    ap.add_argument(
        "--backend", default=None,
        help="backend override for --klt-row-evidence (default: klt's own / $KLT_SIM_BACKEND)",
    )
    evidence.add_supersedes_argument(ap)
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

    if args.probe_klt_row:
        return run_row_probe()

    if args.klt_row_evidence:
        return run_row_evidence_campaign(
            record=args.record, backend=args.backend, quiet=args.quiet,
            supersedes=args.supersedes,
        )

    if args.corners:
        return run_corner_campaign(
            record=args.record, quiet=args.quiet, supersedes=args.supersedes
        )

    return run(record=args.record, supersedes=args.supersedes)


if __name__ == "__main__":
    raise SystemExit(main())

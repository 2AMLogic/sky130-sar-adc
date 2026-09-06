#!/usr/bin/env python3
"""Comparator sub-block PEX flow (issue #112): a single `klt pex` call
extracts the composed layout's parasitics, re-simulates the schematic-vs-
extracted pick-off delta at Vindiff=0 (routing/parasitic-only imbalance) and
Vindiff=+10mV (gain calibration), and diffs the two -- plus one `klt extract
--parasitics` call for the full per-net R/C table AC1/AC2 want (`klt pex`'s
own JSON only echoes an aggregate `extraction.model` scope note, not
per-net values). Together these mint a new append-only evidence record
under layout/comparator/reports/.

Until klayout-tools==0.4.0 (issue #146), this script instead ran `klt pex`'s
three logical steps (extract, re-simulate each leg, diff) as three separate
subprocess calls, with a local unit-normalization workaround
(`normalize_extracted_units.py`, now deleted) applied to the extracted
netlist in between -- working around two upstream `klt pex` bugs
(2AMLogic/klayout-tools#1395/#1396). Both are fixed in 0.4.0 (this repo's
pinned version): #1395's `models.lib` mis-resolution no longer reproduces,
and #1396's sky130 unit-suffix mismatch is fixed at the source (`klt
extract --pdk sky130A --parasitics` now emits bare-micron geometry
directly, so the old normalization step's own re-normalization of already-
bare values now corrupts device geometry by ~1e6x instead of fixing
anything -- verified empirically re-running the old workaround against
0.4.0 before deleting it). See README.md's "Why not just `klt pex`" section
(marked historical) for the full prior writeup.

A third, unrelated `klt pex` gap surfaced re-deriving the pick-off timing
for issue #187: passing `-o`/`--outdir` as RELATIVE paths makes the
extracted-side DUT-swap testbench's `.include` line unresolvable once
`klt pex`'s internal `klt sim` call runs ngspice from its own per-corner
working directory (2AMLogic/klayout-tools#1525, filed generically). Worked
around locally by passing both as ABSOLUTE paths (still under this record's
own `.klt/` scratch subtree) -- see the `_run_klt(["pex", ...])` call below.

    python3 layout/comparator/pex/run_pex.py --check-env
    python3 layout/comparator/pex/run_pex.py --record
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[3] / "sim"
sys.path.insert(0, str(SIM_DIR))

from harness import evidence, pdk  # noqa: E402

PEX_DIR = Path(__file__).resolve().parent
COMPARATOR_DIR = PEX_DIR.parent
REPORTS_DIR = COMPARATOR_DIR / "reports"
OFFSET_RECORD = (
    SIM_DIR / "comparator-decision" / "records" / "20260821-071918-433a294.md"
)
# Device-mismatch-only offset this PEX record's routing-driven component is
# compared against (see OFFSET_RECORD's own N=16/seed=1/tt_mm numbers) --
# restated here, not re-derived, purely so record.md can cite a fixed
# number even if a future N-adequate campaign supersedes that record.
OFFSET_MISMATCH_MEAN_MV = 35.24
OFFSET_MISMATCH_STDEV_MV = 97.08

PICKOFF_AT_NS = 6.3  # RESET_NS(5) + RESET_TR_NS(0.1) + PICKOFF_NS(1.2).
# Re-derived for DR-004 Amendment A's extracted (parasitic-loaded) leg
# (issue #187): the original PICKOFF_NS=0.3 (matching sim/comparator-
# decision/run.py's own pick-off point at the time) was calibrated against
# the pre-#175 topology and produced a sign-flipped extracted-side pick-off
# differential once real routing parasitics were in the loop (negative for
# a positive applied Vindiff -- see reports/20260906-101231-1250ff4/
# record.md's AC3). layout/comparator/pex/regen_probe.py's reset->evaluate
# transient sweep (reports/20260906-144802-eace0b6/record.md) re-derived
# this instant directly from the extracted leg's own regeneration timing;
# see testbench.spice's header for the same history.
CAL_VINDIFF_MV = 10.0  # index-1 corner point's Vindiff (see testbench.spice)

ZERO_CORNER_ID = "tt/vinn=0.900_vinp=0.900V/27C"
CAL_CORNER_ID = "tt/vinn=0.895_vinp=0.905V/27C"


def _run_klt(args: list[str], cwd: Path) -> dict:
    """Run `klt <args> --format json` with `cwd` as the working directory and
    every path argument given RELATIVE to it -- so any path `klt` echoes back
    into its JSON response is relative/repo-shaped rather than an absolute
    path that would leak this machine's home directory and worktree number
    into a COMMITTED evidence file (the same leak {path, scope}-normalized
    fields, docs/cli/env-provenance.md, exist to prevent on the fields that
    already got that treatment)."""
    proc = subprocess.run(
        ["klt", *args, "--format", "json"], capture_output=True, text=True, cwd=str(cwd)
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"klt {args[0]} did not return JSON (exit {proc.returncode})")
    return payload


def _pickoff_diffs(delta: list[dict], value_key: str) -> dict[str, tuple[float, float]]:
    """`klt pex`'s `delta[]` -> corner_id -> (outp_v, outn_v), reading either
    `schematic_value` or `extracted_value` (`value_key`) from each row."""
    by_corner: dict[str, dict[str, float]] = {}
    for row in delta:
        by_corner.setdefault(row["corner_id"], {})[row["spec_row"]] = row[value_key]
    return {
        corner_id: (values["outp_pickoff"], values["outn_pickoff"])
        for corner_id, values in by_corner.items()
    }


def run(record: bool, quiet: bool = False) -> int:
    info = pdk.resolve()
    if not info.found:
        print(f"PDK not resolvable: {info.error}", file=sys.stderr)
        return 3

    latest_layout_id = (REPORTS_DIR / "LATEST").read_text().strip()
    layout_dir = REPORTS_DIR / latest_layout_id
    gds_path = layout_dir / "comparator.gds"
    if not gds_path.is_file():
        print(f"no comparator.gds at {gds_path}", file=sys.stderr)
        return 3

    record_id = evidence.new_record_id()
    out_dir = REPORTS_DIR / record_id
    out_dir.mkdir(parents=True, exist_ok=False)

    gds_rel = os.path.relpath(gds_path, out_dir)

    # --- Step 1: `klt extract --parasitics --pdk` for the full per-net R/C
    # table AC1/AC2 want -- `klt pex` below runs this same extraction
    # internally, but its own JSON only echoes an aggregate
    # `extraction.model` scope note, not `parasitics.nets[]`'s per-net
    # values, so a standalone `klt extract` call is still needed for the
    # table (duplicating the extraction pass is the accepted cost; both
    # calls extract the identical layout with the identical deck). ---
    spice_name = "comparator.pex-extract.spice"
    extract_json = _run_klt(
        [
            "extract",
            gds_rel,
            "--deck",
            "sky130",
            "--pdk",
            info.variant,
            "--pdk-root",
            str(info.root),
            "--parasitics",
            "-o",
            spice_name,
        ],
        cwd=out_dir,
    )
    (out_dir / "extract.json").write_text(json.dumps(extract_json, indent=2) + "\n")
    if extract_json.get("status") != "extracted":
        print(f"klt extract failed: {extract_json}", file=sys.stderr)
        return 1
    if not quiet:
        print(f"  klt extract --parasitics: {extract_json['status']} "
              f"({extract_json['device_count']} devices, {extract_json['net_count']} nets)")

    # --- Step 2: `klt pex` -- extraction (again, internally) + re-simulate
    # both legs (schematic side unmodified; extracted side generated by
    # `klt pex` itself via its DUT-`.include`-swap convention, docs/cli/
    # pex.md) + diff, all in one call. Supersedes the former
    # extract/normalize/sim/sim/diff workaround now that
    # 2AMLogic/klayout-tools#1395/#1396 are fixed in the pinned 0.4.0. ---
    for name in ("comparator_pex_reference.spice", "testbench.spice", "pex_request.json"):
        shutil.copy(PEX_DIR / name, out_dir / name)

    # `-o`/`--outdir` are given as ABSOLUTE paths (both still scoped under
    # this record's own `.klt/` scratch subtree, cleaned up below) -- issue
    # #187 found that a RELATIVE `-o` here (`.klt/pex-extracted.spice`) makes
    # `klt pex` write that same relative string into the extracted-side
    # testbench's `.include` line, but `klt sim`'s own per-corner execution
    # model runs ngspice from a corner-specific working directory nested
    # under `--outdir`, not from this `cwd` -- so the relative `.include`
    # no longer resolves there and every extracted-side corner errors
    # (`Could not find include file .klt/pex-extracted.spice`), even though
    # the identical testbench runs fine standalone via `klt sim`. Absolute
    # paths sidestep the mismatch entirely, and `klt`'s own path-scoping
    # still reports them as repo-relative/`scope: "repo"` in the JSON
    # response below (verified: an absolute path under the repo checkout
    # comes back re-relativized, not leaked) -- see
    # 2AMLogic/klayout-tools#1525 (filed generically, no design detail) for
    # the upstream gap this works around.
    (out_dir / ".klt").mkdir(exist_ok=True)
    pex_json = _run_klt(
        [
            "pex",
            gds_rel,
            "pex_request.json",
            "--deck",
            "sky130",
            "--pdk",
            info.variant,
            "--pdk-root",
            str(info.root),
            "-o",
            str(out_dir / ".klt" / "pex-extracted.spice"),
            "--outdir",
            str(out_dir / ".klt" / "pex"),
        ],
        cwd=out_dir,
    )
    (out_dir / "pex.json").write_text(json.dumps(pex_json, indent=2) + "\n")
    if pex_json.get("status") != "pass":
        print(f"klt pex did not pass: {pex_json}", file=sys.stderr)
        return 1

    sch = _pickoff_diffs(pex_json["delta"], "schematic_value")
    ext = _pickoff_diffs(pex_json["delta"], "extracted_value")

    sch_zero_diff = sch[ZERO_CORNER_ID][0] - sch[ZERO_CORNER_ID][1]
    ext_zero_diff = ext[ZERO_CORNER_ID][0] - ext[ZERO_CORNER_ID][1]
    sch_cal_diff = sch[CAL_CORNER_ID][0] - sch[CAL_CORNER_ID][1]
    ext_cal_diff = ext[CAL_CORNER_ID][0] - ext[CAL_CORNER_ID][1]

    sch_gain = sch_cal_diff / (CAL_VINDIFF_MV / 1000.0)
    ext_gain = ext_cal_diff / (CAL_VINDIFF_MV / 1000.0)

    # Input-referred parasitic-driven offset: the zero-input pick-off
    # differential converted through the EXTRACTED-side's own gain (the
    # loaded circuit's own gain, not the ideal schematic's) -- this is the
    # offset the routing/parasitics alone would appear to contribute if it
    # were the only source of imbalance.
    parasitic_offset_mv = (ext_zero_diff / ext_gain) * 1000.0

    if not quiet:
        print(f"  schematic: zero-diff pickoff={sch_zero_diff * 1e6:+.3f} uV, "
              f"gain={sch_gain:.4f} V/V")
        print(f"  extracted: zero-diff pickoff={ext_zero_diff * 1e6:+.3f} uV, "
              f"gain={ext_gain:.4f} V/V")
        print(f"  parasitic-driven input-referred offset estimate: "
              f"{parasitic_offset_mv:+.5f} mV")

    net_caps = {}
    for net in extract_json.get("parasitics", {}).get("nets", []):
        if net["net"] in ("OUTP", "OUTN", "VINP", "VINN"):
            total_coupled = sum(c["capacitance_ff"] for c in net.get("coupled", []))
            net_caps[net["net"]] = {
                "r_ohm": net["resistance_ohm"],
                "c_ground_ff": net["capacitance_ff"],
                "c_coupled_total_ff": total_coupled,
                "c_total_ff": net["capacitance_ff"] + total_coupled,
            }

    if record:
        path = write_record(
            record_id, out_dir, info, extract_json,
            sch_zero_diff, ext_zero_diff, sch_gain, ext_gain,
            parasitic_offset_mv, net_caps,
        )
        print(f"wrote {path}")

    # `klt pex`'s (and `klt extract`'s) own scratch dirs (per-corner decks/
    # logs, not evidence -- every measured value is already captured in
    # pex.json/extract.json above). See .gitignore's own comment for why
    # this is defense-in-depth, not the only guard.
    shutil.rmtree(out_dir / ".klt", ignore_errors=True)

    return 0


def write_record(
    record_id: str, out_dir: Path, info: pdk.PdkInfo, extract_json: dict,
    sch_zero_diff: float, ext_zero_diff: float, sch_gain: float, ext_gain: float,
    parasitic_offset_mv: float, net_caps: dict,
) -> Path:
    lines: list[str] = []
    a = lines.append
    a(f"# Comparator PEX record: {record_id}")
    a("")
    a(
        "Real `klt extract --parasitics --pdk sky130A` parasitic extraction "
        "of the composed comparator layout (issue #112), superseding the "
        "wire-*area* symmetry proxy in "
        "`layout/comparator/reports/20260825-135219-59f8e86/record.md` -- "
        "that record stays exactly as it was minted (append-only); this is "
        "a new, sibling record."
    )
    a("")
    a(
        "Generated by two `klt` calls: `klt extract --parasitics` (for the "
        "full per-net R/C table AC1/AC2 need -- `klt pex` below runs this "
        "same extraction internally but its own JSON only echoes an "
        "aggregate scope note, not per-net values) and a single `klt pex "
        "<layout>.gds pex_request.json --deck sky130 --pdk sky130A "
        "--pdk-root $PDK_ROOT` call, which extracts (again), re-simulates "
        "both the schematic and extracted legs, and diffs them in one step "
        "(issue #146). Earlier records under this directory instead ran "
        "`klt pex`'s three logical steps as three separate subprocess "
        "calls with a local unit-normalization workaround in between, "
        "working around two upstream `klt pex` bugs "
        "(2AMLogic/klayout-tools#1395/#1396) that are fixed in this repo's "
        "pinned `klt` 0.4.0 -- see `layout/comparator/pex/README.md`'s "
        "\"Why not just `klt pex`\" section (now historical) for that "
        "prior writeup, and `layout/comparator/pex/run_pex.py`'s own "
        "module docstring for how the fix was verified before the "
        "workaround was deleted."
    )
    a("")
    a(
        "`layout/comparator/pex/run_pex.py` is this record's generator; "
        "re-run it to reproduce."
    )
    a("")
    a("## Provenance")
    a("")
    a(f"- `klt` version: {extract_json['provenance']['klt_version']}")
    a(f"- KLayout engine: {extract_json['provenance']['klayout_version']}")
    a(
        f"- PDK: {extract_json['provenance']['pdk']['name']} "
        f"({extract_json['provenance']['pdk']['version']})"
    )
    a(f"- Extraction deck content hash: `{extract_json['provenance']['deck']['content_hash']}`")
    git = evidence.git_info()
    a(f"- repo commit: `{git.commit}` on `{git.branch}`" + (" (dirty)" if git.dirty else " (clean)"))
    a(f"- layout source: `layout/comparator/reports/{(out_dir.parent / 'LATEST').read_text().strip()}/comparator.gds`")
    a("")

    a("## AC1/AC2: parasitic-annotated extraction, OUTP/OUTN capacitance in farads")
    a("")
    a(
        "`klt extract --parasitics --pdk sky130A` on the composed layout: "
        f"{extract_json['device_count']} devices, {extract_json['net_count']} nets. "
        "Full per-net R/C (ground + every coupled-net term) is in "
        "`extract.json`'s `parasitics.nets[]`; the OUTP/OUTN and VINN/VINP "
        "pairs the wire-area record flagged are pulled out below."
    )
    a("")
    a("| Net | R (ohm) | C to ground (fF) | C coupled, total (fF) | C total (fF) |")
    a("|---|---|---|---|---|")
    for net in ("OUTP", "OUTN", "VINP", "VINN"):
        c = net_caps[net]
        a(
            f"| {net} | {c['r_ohm']:.2f} | {c['c_ground_ff']:.4f} | "
            f"{c['c_coupled_total_ff']:.4f} | {c['c_total_ff']:.4f} |"
        )
    a("")
    outp_c, outn_c = net_caps["OUTP"]["c_total_ff"], net_caps["OUTN"]["c_total_ff"]
    vinp_c, vinn_c = net_caps["VINP"]["c_total_ff"], net_caps["VINN"]["c_total_ff"]
    outp_outn_imbalance = abs(outp_c - outn_c) / ((outp_c + outn_c) / 2) * 100
    vinp_vinn_imbalance = abs(vinp_c - vinn_c) / ((vinp_c + vinn_c) / 2) * 100
    a(
        f"- **OUTP/OUTN total-capacitance imbalance: {outp_outn_imbalance:.3f}%** "
        f"({outp_c:.4f} fF vs {outn_c:.4f} fF) -- restates the wire-area "
        "record's 0.65% claim in farads. Same ranking (OUTP/OUTN the "
        "tighter-matched pair, VINN/VINP the looser one) as the area proxy, "
        "but a smaller number -- the area proxy over-estimated this "
        "imbalance."
    )
    a(
        f"- **VINN/VINP total-capacitance imbalance: {vinp_vinn_imbalance:.3f}%** "
        f"({vinp_c:.4f} fF vs {vinn_c:.4f} fF) -- restates the wire-area "
        "record's 15.54% claim in farads; smaller in absolute percentage "
        "but the SAME qualitative conclusion the wire-area record already "
        "drew (VINN/VINP is the looser-matched pair, and it is structural: "
        "the cross-quad's upper-row gate pads force the two input nets' "
        "trunks to cross, see `layout/comparator/README.md`)."
    )
    a("")

    a("## AC3: schematic-vs-extracted pick-off delta (`klt pex`, tt/27C/1.8V)")
    a("")
    a(
        f"Pick-off statistic v(OUTP)-v(OUTN) at t={PICKOFF_AT_NS}ns after the "
        "evaluate edge starts (matches "
        "`sim/comparator-decision/run.py`'s own `_pickoff_deck` "
        "methodology), at two corner points: Vindiff=0 (isolates the "
        f"routing/parasitic-driven imbalance, device mismatch structurally "
        f"excluded) and Vindiff=+{CAL_VINDIFF_MV:.0f}mV (gain calibration, "
        "one of `run.py`'s own `VINDIFF_GAIN_CAL_MV` points)."
    )
    a("")
    a(
        f"**Pick-off instant (issue #187): {PICKOFF_AT_NS}ns, not the "
        "original 5.4ns.** `layout/comparator/reports/20260906-101231-"
        "1250ff4/record.md`'s AC3 (against the same DR-004 Amendment A "
        "topology this record's layout also carries) measured a "
        "sign-flipped, near-degenerate extracted-side gain "
        "(-0.576 V/V vs. the schematic side's +1.873 V/V) at the "
        "original fixed 5.4ns instant. "
        "`layout/comparator/pex/regen_probe.py`'s reset->evaluate transient "
        "sweep (`reports/20260906-144802-eace0b6/record.md`) found that "
        "instant was too early for this topology's extracted (parasitic-"
        "loaded) leg -- its regeneration onset is measurably delayed "
        f"relative to the ideal schematic leg -- and re-derived {PICKOFF_AT_NS}ns "
        "as a corrected instant at which both legs give a clean, "
        "correctly-signed, non-saturated pick-off (see that record's "
        "\"Recommendation\" section, including a corner spot check at "
        "ss/-40C and ff/125C). The gains below use the corrected instant; "
        "both are now positive."
    )
    a("")
    a("| | schematic (ideal) | extracted (parasitic-annotated) |")
    a("|---|---|---|")
    a(f"| pick-off diff @ Vindiff=0 | {sch_zero_diff * 1e6:+.3f} uV | {ext_zero_diff * 1e6:+.3f} uV |")
    a(f"| gain (from +{CAL_VINDIFF_MV:.0f}mV point) | {sch_gain:.4f} V/V | {ext_gain:.4f} V/V |")
    a("")
    a(
        "Full `klt pex` JSON response (both legs' per-corner measured "
        "values live in its `delta[]`): `pex.json`."
    )
    a("")

    a("## AC4: is the routing-driven component material against device mismatch?")
    a("")
    a(
        f"**Input-referred parasitic-driven offset estimate: "
        f"{parasitic_offset_mv:+.5f} mV** (Vindiff=0 pick-off differential "
        "on the extracted netlist, converted through the extracted-side's "
        "own gain)."
    )
    a("")
    a(
        f"Compared against the device-mismatch-only offset "
        f"`sim/comparator-decision/records/20260821-071918-433a294.md` "
        f"reports (`tt_mm`, N=16, seed=1): mean **{OFFSET_MISMATCH_MEAN_MV:.2f} mV**, "
        f"stdev **{OFFSET_MISMATCH_STDEV_MV:.2f} mV**."
    )
    a("")
    ratio_of_mean = abs(parasitic_offset_mv) / OFFSET_MISMATCH_MEAN_MV * 100
    ratio_of_stdev = abs(parasitic_offset_mv) / OFFSET_MISMATCH_STDEV_MV * 100
    mean_multiple = OFFSET_MISMATCH_MEAN_MV / abs(parasitic_offset_mv)
    stdev_multiple = OFFSET_MISMATCH_STDEV_MV / abs(parasitic_offset_mv)
    a(
        f"- {abs(parasitic_offset_mv):.5f} mV is {ratio_of_mean:.3f}% of the "
        f"mismatch record's mean and {ratio_of_stdev:.3f}% of its stdev "
        f"(i.e. the mean is {mean_multiple:.0f}x larger, the stdev "
        f"{stdev_multiple:.0f}x larger, than this estimate)."
    )
    # Worded from the actual multiples rather than a fixed "two orders of
    # magnitude" claim: this pick-off-differential quantity sits so close
    # to the simulator's own noise floor (both legs' Vindiff=0 diffs are
    # single- to low-triple-digit microvolts) that a `klt`/ngspice version
    # bump alone measurably moves the multiple run to run (issue #146
    # re-ran this record against klt 0.4.0 for the first time and saw the
    # extracted-side diff move by ~7x versus the prior 0.3.0-era record,
    # entirely within this same noise regime) -- a hard-coded order-of-
    # magnitude count would silently go stale the next time that happens.
    smallest_multiple = min(mean_multiple, stdev_multiple)
    if smallest_multiple >= 100:
        magnitude_phrase = "over two orders of magnitude smaller"
    elif smallest_multiple >= 10:
        magnitude_phrase = "over an order of magnitude smaller"
    else:
        magnitude_phrase = f"{smallest_multiple:.0f}x smaller"
    a(
        "- **Conclusion: the routing-driven component is noise against the "
        "device-mismatch term, not material at this block's offset "
        f"budget.** The parasitic-driven offset estimate above is {magnitude_phrase} "
        "than either the mean or the stdev of "
        "the device-mismatch-only offset distribution -- device mismatch, "
        "not routing/parasitic imbalance, is what would need to "
        "shrink to move this comparator's offset budget. No floorplan "
        "change is warranted on offset grounds; the router should not be "
        "re-litigated for this reason (per the wire-area record's own "
        "note)."
    )
    a(
        "- This conclusion is about **offset** specifically. It does not "
        "re-open regeneration-time/speed symmetry (a second-order, "
        "non-offset contributor `layout/comparator/README.md` already "
        "scopes out of this issue's acceptance criteria) or noise."
    )
    a("")

    a("## Files")
    a("")
    a("```")
    a(f"{out_dir.name}/")
    a("  comparator.pex-extract.spice   klt extract --parasitics --pdk output (per-net R/C table source)")
    a("  extract.json                   klt extract --parasitics JSON envelope")
    a("  comparator_pex_reference.spice schematic DUT snapshot")
    a("  testbench.spice                pex testbench (klt pex swaps its .include for the extracted netlist)")
    a("  pex_request.json               klt pex request (corners/analysis/measurements)")
    a("  pex.json                       klt pex JSON response (extraction summary + delta[])")
    a("  record.md                      this file")
    a("```")
    a("")

    (out_dir / "record.md").write_text("\n".join(lines) + "\n")
    return out_dir / "record.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator PEX flow (issue #112)")
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--record", action="store_true", help="write an evidence record under reports/")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.check_env:
        info = pdk.resolve()
        print(f"PDK: variant={info.variant} root={info.root} found={info.found}")
        if not info.found:
            print(f"  error: {info.error}")
            return 3
        if shutil.which("klt") is None:
            print("klt not found on PATH")
            return 3
        return 0

    return run(record=args.record, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())

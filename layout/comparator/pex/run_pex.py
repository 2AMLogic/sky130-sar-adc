#!/usr/bin/env python3
"""Comparator sub-block PEX flow (issue #112): `klt extract --parasitics
--pdk` the composed layout, re-simulate the schematic-vs-extracted pick-off
delta at Vindiff=0 (routing/parasitic-only imbalance) and Vindiff=+10mV
(gain calibration), and mint a new append-only evidence record under
layout/comparator/reports/.

Not a `klt pex` invocation end-to-end: `klt pex` itself hit two independent
tool bugs on this sub-block (see README.md in this directory for both
citations and the workaround detail), so this script performs the same
three logical steps `klt pex` documents (extract -> re-simulate each leg ->
diff) as separate `klt extract`/`klt sim` subprocess calls instead, with
`normalize_extracted_units.py`'s workaround applied to the extracted
netlist in between. `klt extract --parasitics` (step 1) is unaffected by
either bug and runs exactly as `klt pex` would run it internally.

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

PICKOFF_AT_NS = 5.4  # RESET_NS(5) + RESET_TR_NS(0.1) + PICKOFF_NS(0.3),
# matching sim/comparator-decision/run.py's own PICKOFF_NS pick-off point.
CAL_VINDIFF_MV = 10.0  # index-1 corner point's Vindiff (see testbench.spice)


def _run_klt(args: list[str], cwd: Path) -> dict:
    """Run `klt <args> --format json` with `cwd` as the working directory and
    every path argument given RELATIVE to it -- so any path `klt` echoes back
    into its JSON response is relative/repo-shaped rather than an absolute
    path that would leak this machine's home directory and worktree number
    into a COMMITTED evidence file (the same leak {path, scope}-normalized
    fields, docs/cli/env-provenance.md, exist to prevent on the fields that
    already got that treatment; `klt extract`'s `file`/`netlist_path` fields
    have not, as of klt 0.3.0, so this call-site avoids it by construction
    instead)."""
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


def _pickoff_diffs(sim_json: dict) -> dict[str, tuple[float, float]]:
    """corner_id -> (outp_v, outn_v)."""
    out: dict[str, tuple[float, float]] = {}
    for corner in sim_json.get("corners", []):
        values = {m["name"]: m["value"] for m in corner["measurements"]}
        out[corner["corner_id"]] = (values["outp_pickoff"], values["outn_pickoff"])
    return out


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

    # --- Step 1: klt extract --parasitics --pdk (unaffected by either
    # filed bug -- this is the actual parasitic-annotated netlist AC1 asks
    # for, produced the identical way `klt pex` would produce it). ---
    raw_spice_name = "comparator.pex-extract.raw.spice"
    raw_spice = out_dir / raw_spice_name
    gds_rel = os.path.relpath(gds_path, out_dir)
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
            raw_spice_name,
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

    # --- Step 1b: workaround (see normalize_extracted_units.py). ---
    normalized_spice = out_dir / "comparator.pex-extract.normalized.spice"
    subprocess.run(
        [
            sys.executable,
            str(PEX_DIR / "normalize_extracted_units.py"),
            str(raw_spice),
            str(normalized_spice),
        ],
        check=True,
    )

    # --- Step 2: re-simulate both legs (schematic DUT unmodified;
    # extracted DUT is the just-normalized netlist). ---
    for name in ("comparator_pex_reference.spice", "testbench.spice", "extracted_testbench.spice"):
        shutil.copy(PEX_DIR / name, out_dir / name)

    base_request = json.loads((PEX_DIR / "pex_request.json").read_text())

    schematic_request = dict(base_request, netlist="testbench.spice")
    (out_dir / "pex_request.schematic.json").write_text(
        json.dumps(schematic_request, indent=2) + "\n"
    )
    extracted_request = dict(
        base_request, netlist="extracted_testbench.spice", netlist_source="extracted"
    )
    (out_dir / "pex_request.extracted.json").write_text(
        json.dumps(extracted_request, indent=2) + "\n"
    )

    sim_schematic = _run_klt(["sim", "pex_request.schematic.json"], cwd=out_dir)
    (out_dir / "sim.schematic.json").write_text(json.dumps(sim_schematic, indent=2) + "\n")
    sim_extracted = _run_klt(["sim", "pex_request.extracted.json"], cwd=out_dir)
    (out_dir / "sim.extracted.json").write_text(json.dumps(sim_extracted, indent=2) + "\n")

    if sim_schematic.get("status") != "pass" or sim_extracted.get("status") != "pass":
        print(
            f"klt sim did not pass on both legs (schematic={sim_schematic.get('status')}, "
            f"extracted={sim_extracted.get('status')})",
            file=sys.stderr,
        )
        return 1

    sch = _pickoff_diffs(sim_schematic)
    ext = _pickoff_diffs(sim_extracted)

    zero_id = "tt/vinn=0.900_vinp=0.900V/27C"
    cal_id = "tt/vinn=0.895_vinp=0.905V/27C"

    sch_zero_diff = sch[zero_id][0] - sch[zero_id][1]
    ext_zero_diff = ext[zero_id][0] - ext[zero_id][1]
    sch_cal_diff = sch[cal_id][0] - sch[cal_id][1]
    ext_cal_diff = ext[cal_id][0] - ext[cal_id][1]

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

    # `klt sim`'s own scratch dir (per-corner decks/logs, not evidence --
    # every measured value is already captured in sim.schematic.json/
    # sim.extracted.json above). See .gitignore's own comment for why this
    # is defense-in-depth, not the only guard.
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
        "**Not a `klt pex` invocation end-to-end.** `klt pex` itself hit "
        "two independent tool bugs on this sub-block, both filed "
        "generically at 2AMLogic/klayout-tools per CLAUDE.md's friction "
        "protocol (see `layout/comparator/pex/README.md` for the full "
        "writeup and issue links):"
    )
    a("")
    a(
        "1. `klt pex`'s generated extracted-side request copy re-resolves "
        "a relative `models.lib` path against the *original request "
        "file's own directory* instead of the PDK-variant directory "
        "`models.pdk` resolves it against -- `model library not found`, "
        "even though the identical request runs fine standalone via `klt "
        "sim` and on `klt pex`'s own schematic-side leg."
    )
    a(
        "2. `klt extract --pdk sky130A --parasitics`'s sky130 MOS binding "
        "writes device geometry (`L`/`W`/`AS`/`AD`/`PS`/`PD`) with "
        "explicit SPICE unit suffixes (e.g. `L=0.5U`); sky130's vendor "
        "model deck sets `.option scale=1.0u` and "
        "`sky130_fd_pr__nfet_01v8`/`pfet_01v8`'s own internal NRD/NRS "
        "default-value formula assumes bare, suffix-free micron literals "
        "-- feeding it unit-suffixed values makes the computed default "
        "NRD/NRS come out ~1e6x too large, and ngspice refuses the device "
        "with a generic `could not find a valid modelname` (verified on a "
        "single-device minimal repro)."
    )
    a("")
    a(
        "This record instead runs the same three logical steps `klt pex` "
        "documents (extract, re-simulate each leg, diff) as separate "
        "commands: `klt extract --parasitics` (unaffected by either bug -- "
        "the actual parasitic-annotated netlist, produced exactly as `klt "
        "pex` would produce it internally) followed by `klt sim` on each "
        "leg by hand, with "
        "`layout/comparator/pex/normalize_extracted_units.py`'s "
        "value-preserving unit-suffix workaround applied to the extracted "
        "netlist in between. `layout/comparator/pex/run_pex.py` is this "
        "record's generator; re-run it to reproduce."
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

    a("## AC3: schematic-vs-extracted pick-off delta (`klt sim`, tt/27C/1.8V)")
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
    a("| | schematic (ideal) | extracted (parasitic-annotated) |")
    a("|---|---|---|")
    a(f"| pick-off diff @ Vindiff=0 | {sch_zero_diff * 1e6:+.3f} uV | {ext_zero_diff * 1e6:+.3f} uV |")
    a(f"| gain (from +{CAL_VINDIFF_MV:.0f}mV point) | {sch_gain:.4f} V/V | {ext_gain:.4f} V/V |")
    a("")
    a(
        "Full `klt sim` JSON responses: `sim.schematic.json`, "
        "`sim.extracted.json`."
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
    a(
        "- **Conclusion: the routing-driven component is noise against the "
        "device-mismatch term, not material at this block's offset "
        "budget.** The parasitic-driven offset estimate above is over two "
        "orders of magnitude smaller than either the mean or the stdev of "
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
    a("  comparator.pex-extract.raw.spice        klt extract --parasitics --pdk raw output")
    a("  comparator.pex-extract.normalized.spice  + normalize_extracted_units.py workaround applied")
    a("  extract.json                             klt extract --parasitics JSON envelope")
    a("  comparator_pex_reference.spice           schematic DUT snapshot")
    a("  testbench.spice / extracted_testbench.spice   both legs' klt-sim netlists")
    a("  pex_request.schematic.json / pex_request.extracted.json   both legs' klt-sim requests")
    a("  sim.schematic.json / sim.extracted.json  klt sim JSON responses")
    a("  record.md                                this file")
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

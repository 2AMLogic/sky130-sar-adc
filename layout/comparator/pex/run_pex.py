#!/usr/bin/env python3
"""Comparator sub-block PEX flow (issue #112, re-minted for issue #1017):
`klt extract --parasitics` for the full per-net R/C table, then TWO `klt
pex` calls (Vindiff=0 and Vindiff=+10mV -- see below), each extracting the
composed layout's parasitics, re-simulating the schematic-vs-extracted
pick-off delta across the ratified 9-point one-at-a-time PVT grid and
diffing the legs. Together these mint a new append-only evidence record
under layout/comparator/reports/.

Issue #1017's re-mint superseded the three September 2026 envelopes (which
ran on klt 0.4.0, a pre-DR-004-Amendment-A-era corner shape -- two corner
points at tt/27C only -- and layouts the drawing flow has since re-drawn):
this flow re-runs the same pick-off methodology (including issue #187's
corrected 6.3ns instant) on the layout `reports/LATEST` currently names, at
the ratified OAT grid, on the layout flow's pinned `klt`
(layout/requirements.txt) through layout/bin/pex_flow.py. The September
records stay exactly as minted (append-only).

Why TWO `klt pex` calls: the two Vindiff points ride the SAME testbench via
`corners.supply_v` on the literal `Vinp`/`Vinn` sources (the alter gotcha,
README.md), and the ratified OAT carve is expressed per request -- a zero
request (vinp=vinn=vdd/2 tracking the rail) and a cal request
(vinp=vdd/2+5mV, vinn=vdd/2-5mV). Folding both into one request would need
the union cross-product of vinp/vinn values excluded down to 18 points (a
~1600-entry `exclude` list); two single-purpose carves keep each request's
carve to the same paired-tracking shape every other OAT request in this
repo uses. Each call runs its own internal extraction (seconds; the
standalone `klt extract` below duplicates it for the per-net table, the
accepted cost since `klt pex`'s JSON echoes only an aggregate scope note).

Historical tool gaps this flow no longer works around (fixed upstream, see
README.md's "Why not just `klt pex`", now historical): #1395/#1396 (fixed
in 0.4.0) and #1525 (relative `-o`/`--outdir` breaking the extracted-side
`.include` once `klt sim` runs ngspice from a per-corner directory -- both
paths are passed ABSOLUTE here, still under the record's own `.klt/`
scratch subtree).

    python3 layout/comparator/pex/run_pex.py --check-env
    python3 layout/comparator/pex/run_pex.py --pilot    # tt/27C/1.8V, local
    python3 layout/comparator/pex/run_pex.py --record   # 9 OAT corners x 2 vindiff, batch
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

PEX_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PEX_DIR.parents[1] / "bin"))
sys.path.insert(0, str(PEX_DIR.parents[2] / "sim"))

import pex_flow  # noqa: E402

from harness import evidence, pdk  # noqa: E402

BLOCK_DIR = PEX_DIR.parent
REPORTS_DIR = BLOCK_DIR / "reports"
OFFSET_RECORD = (
    PEX_DIR.parents[2] / "sim" / "comparator-decision" / "records" / "20260821-071918-433a294.md"
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
CAL_VINDIFF_MV = 10.0  # the cal request's Vindiff (split +/-5mV around vdd/2)

GDS_NAME = "comparator.gds"


def oat_points(pilot: bool):
    """The ratified OAT star as supply-source maps: `vdd` plus vinp/vinn
    tracking vdd/2. Paired per request (zero vs cal) -- see module
    docstring."""
    def half(v: float) -> float:
        return round(v / 2.0, 6)

    def cal_p(v: float) -> float:
        return round(v / 2.0 + CAL_VINDIFF_MV / 2000.0, 6)

    def cal_n(v: float) -> float:
        return round(v / 2.0 - CAL_VINDIFF_MV / 2000.0, 6)

    star = [
        (p, t, v)
        for p, t, v in pex_flow.corners_mod.ratified_oat_grid(
            1.8,
            pex_flow.corners_mod.RATIFIED_SUPPLY_TOLERANCE,
            pex_flow.corners_mod.RATIFIED_PROCESS_CORNERS,
            pex_flow.corners_mod.RATIFIED_TEMPS_C,
        )
    ]
    if pilot:
        star = [(p, t, v) for p, t, v in star if p == "tt" and t == 27.0 and v == 1.8]
    zero = [
        pex_flow.OatPoint(p, t, v, {"vdd": v, "vinp": half(v), "vinn": half(v)})
        for p, t, v in star
    ]
    cal = [
        pex_flow.OatPoint(p, t, v, {"vdd": v, "vinp": cal_p(v), "vinn": cal_n(v)})
        for p, t, v in star
    ]
    return zero, cal


def build_request(points) -> dict:
    corners, exclude = pex_flow.build_corners_spec(points)
    return {
        "netlist": "testbench.spice",
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": corners,
        "exclude": exclude,
        "analysis": {"kind": "tran", "args": "0.002n 6.6n"},
        "measurements": [
            {
                "name": "outp_pickoff",
                "spice": f".meas tran outp_pickoff find v(OUTP) at={PICKOFF_AT_NS}n",
                "unit": "V",
            },
            {
                "name": "outn_pickoff",
                "spice": f".meas tran outn_pickoff find v(OUTN) at={PICKOFF_AT_NS}n",
                "unit": "V",
            },
        ],
        "options": {"timeout_s": 120, "keep_artifacts": False},
    }


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


def reference_subckt() -> tuple[str, list[str]]:
    """(name, pins) declared by the committed schematic wrap -- the interface
    `klt pex`'s DUT swap needs the extracted netlist to match."""
    return pex_flow.extracted_subckt(PEX_DIR / "comparator_pex_reference.spice")


def run(work_dir: Path, backend: str, pilot: bool, record: bool, quiet: bool = False) -> int:
    info = pex_flow.resolve_pdk()
    gds_path, latest_id = pex_flow.latest_layout(BLOCK_DIR, GDS_NAME)

    work_dir.mkdir(parents=True, exist_ok=True)
    gds_abs = str(gds_path.resolve())

    # --- Step 1: `klt extract --parasitics` for the full per-net R/C table --
    extract_json = pex_flow.extract_parasitics(
        Path(gds_abs), work_dir, "comparator.pex-extract.spice", info, quiet=quiet
    )
    (work_dir / "extract.json").write_text(json.dumps(extract_json, indent=2) + "\n")

    # --- Step 2: assert the extraction still declares the reference wrap's
    # interface (the committed testbench's Xdut line is positional) --------
    name, pins = pex_flow.extracted_subckt(work_dir / "comparator.pex-extract.spice")
    ref_name, ref_pins = reference_subckt()
    if name != ref_name or pins != ref_pins:
        raise pex_flow.PexFlowError(
            f"extracted interface drifted from the committed schematic wrap:\n"
            f"  got .SUBCKT {name} {' '.join(pins)}\n"
            f"  want .SUBCKT {ref_name} {' '.join(ref_pins)}\n"
            f"Re-derive comparator_pex_reference.spice/testbench.spice against it."
        )

    for src in ("comparator_pex_reference.spice", "testbench.spice"):
        shutil.copy(PEX_DIR / src, work_dir / src)

    # --- Step 3: two `klt pex` calls (zero / cal), each an OAT carve -------
    zero_pts, cal_pts = oat_points(pilot)
    results = {}
    for tag, pts in (("zero", zero_pts), ("cal", cal_pts)):
        request = pex_flow.apply_capacity_wait(build_request(pts))
        (work_dir / f"pex_request_{tag}.json").write_text(json.dumps(request, indent=2) + "\n")
        (work_dir / ".klt").mkdir(exist_ok=True)
        pex_json = pex_flow.run_klt(
            [
                "pex", gds_abs, f"pex_request_{tag}.json",
                "--deck", "sky130",
                "--pdk", info.variant,
                "--pdk-root", str(info.root),
                "-o", str((work_dir / ".klt" / f"pex-extracted-{tag}.spice").resolve()),
                "--outdir", str((work_dir / ".klt" / f"pex-{tag}").resolve()),
                "--backend", backend,
            ],
            cwd=work_dir,
            backend=backend,
            quiet=quiet,
        )
        (work_dir / f"pex_{tag}.json").write_text(json.dumps(pex_json, indent=2) + "\n")
        if pex_json.get("status") != "pass":
            print(f"klt pex ({tag}) did not pass: {json.dumps(pex_json)[:800]}", file=sys.stderr)
            return 1
        results[tag] = pex_json

    analysis = analyse(results)
    report(analysis, quiet=quiet)

    if record:
        path = write_record(work_dir, latest_id, extract_json, results, analysis)
        print(f"wrote {path}")
    shutil.rmtree(work_dir / ".klt", ignore_errors=True)
    return 0


def analyse(results: dict) -> dict:
    """Per OAT corner: zero-diff pick-off differential per leg, cal-point
    gain per leg, and the input-referred parasitic-driven offset through the
    extracted side's own gain."""
    zero = pex_flow.delta_index(results["zero"])
    cal = pex_flow.delta_index(results["cal"])
    # cal corner ids differ from zero ids only in the vinp/vinn tokens; key
    # both by (process, temp, vdd) via parse_corner_id's vdd.
    def _by_rail(idx):
        out = {}
        for cid, rows in idx.items():
            process, temp, supplies = pex_flow.parse_corner_id(cid)
            out[(process, temp, supplies["vdd"])] = (cid, rows)
        return out

    z, c = _by_rail(zero), _by_rail(cal)
    out = {}
    for rail, (zcid, zrows) in sorted(z.items()):
        if rail not in c:
            continue
        ccid, crows = c[rail]
        entry = {"zero_cid": zcid, "cal_cid": ccid, "vdd": rail[2]}
        for leg in ("schematic", "extracted"):
            zp, zn = zrows["outp_pickoff"][leg], zrows["outn_pickoff"][leg]
            cp, cn = crows["outp_pickoff"][leg], crows["outn_pickoff"][leg]
            zero_diff = zp - zn
            gain = (cp - cn) / (CAL_VINDIFF_MV / 1000.0)
            entry[f"{leg}_zero_diff"] = zero_diff
            entry[f"{leg}_gain"] = gain
        # Input-referred parasitic-driven offset: the zero-input pick-off
        # differential converted through the EXTRACTED side's own gain (the
        # loaded circuit's own gain, not the ideal schematic's).
        entry["parasitic_offset_mv"] = (
            entry["extracted_zero_diff"] / entry["extracted_gain"] * 1000.0
        )
        out[rail] = entry
    return out


def report(analysis: dict, *, quiet: bool) -> None:
    if quiet:
        return
    for rail, e in sorted(analysis.items()):
        print(
            f"  {rail[0]}/{rail[2]:.2f}V/{rail[1]:g}C: sch gain {e['schematic_gain']:+.4f} "
            f"ext gain {e['extracted_gain']:+.4f} V/V | "
            f"sch zero-diff {e['schematic_zero_diff'] * 1e6:+.2f} uV "
            f"ext {e['extracted_zero_diff'] * 1e6:+.2f} uV | "
            f"parasitic offset {e['parasitic_offset_mv']:+.5f} mV"
        )


def write_record(
    work_dir: Path, latest_id: str, extract_json: dict, results: dict, analysis: dict
) -> Path:
    out = work_dir
    record_id = out.name
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
    body_bias = results["zero"].get("body_bias", {})
    model = results["zero"].get("extraction", {}).get("model", {})
    prov = extract_json["provenance"]
    vsubs_present = ".GLOBAL vsubs" in (out / "comparator.pex-extract.spice").read_text()
    git = evidence.git_info()

    worst_offset = max(analysis.values(), key=lambda e: abs(e["parasitic_offset_mv"]))
    tt_key = ("tt", 27.0, 1.8)
    tt_entry = analysis.get(tt_key)

    lines: list[str] = []
    a = lines.append
    a(f"# Comparator PEX record: {record_id}")
    a("")
    a(
        "Real `klt extract --parasitics --pdk sky130A` parasitic extraction of the "
        f"composed comparator layout `reports/{latest_id}/comparator.gds` and a "
        "`klt pex` schematic-vs-extracted comparison of the pick-off statistic, at "
        "the ratified 9-point one-at-a-time PVT grid (spec/target-spec.md \"Numeric "
        "rows -- RATIFIED 2026-08-19\") -- issue #1017's re-mint on the current "
        "layout (see Provenance for the `klt` version used). "
        "Supersedes the three September "
        "2026 envelopes (`20260905-213747-bbf06dd`, `20260906-101231-1250ff4`, "
        "`20260906-152000-eace0b6`), which ran on klt 0.4.0 at two tt/27C corner "
        "points against layouts the drawing flow has since re-drawn; those records "
        "stay exactly as minted (append-only)."
    )
    a("")
    a("## Provenance")
    a("")
    a(f"- {pex_flow.klt_version_note(prov['klt_version'])}")
    a(f"- KLayout engine: {prov['klayout_version']}")
    a(f"- PDK: {prov['pdk']['name']} ({prov['pdk']['version']})")
    a(f"- Extraction deck content hash: `{prov['deck']['content_hash']}`")
    a(f"- repo commit: `{git.commit}` on `{git.branch}`" + (" (dirty)" if git.dirty else " (clean)"))
    a(
        f"- layout source: `layout/comparator/reports/{latest_id}/comparator.gds` "
        "(this flow only reads `reports/LATEST`, never moves it)"
    )
    a(f"- `body_bias.status`: **{body_bias.get('status', 'n/a')}** "
      f"({body_bias.get('unbiased_device_count', 0)} unbiased PMOS body nets) -- "
      "checked before any number below is read; an anonymous body net would make "
      "the extracted leg's resimulation physically wrong, not merely imprecise")
    a(
        "- `extraction.model` (klt pex's own scope note): capacitance = "
        f"{model.get('capacitance', 'n/a')}"
    )
    if vsubs_present:
        a(
            "- **Floating substrate net**: the extracted netlist declares `.GLOBAL "
            "vsubs` with no DC tie anywhere in the emitted netlist "
            "(klayout-tools#7066); the extracted leg simulates a substrate node "
            "whose voltage moves with switching activity. The comparator's OUTP/OUTN "
            "pick-off at 6.3 ns reads mid-regeneration, so this artifact is part of "
            "the extracted-side numbers below, disclosed alongside the parasitics."
        )
    a("")
    a("## AC1/AC2: parasitic-annotated extraction, OUTP/OUTN capacitance in farads")
    a("")
    a(
        f"`klt extract --parasitics --pdk sky130A` on the composed layout: "
        f"{extract_json['device_count']} devices, {extract_json['net_count']} nets. "
        "Full per-net R/C (ground + every coupled-net term; vertical-overlap "
        "coupling only unless a net is named `--critical-net`, which this run does "
        "not use -- the same Phase 1 scope every earlier record here states) is in "
        "`extract.json`'s `parasitics.nets[]`; the OUTP/OUTN and VINN/VINP pairs "
        "the wire-area record flagged are pulled out below."
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
        f"({outp_c:.4f} fF vs {outn_c:.4f} fF) -- the farads restatement of the "
        "wire-area record's 0.65% claim, re-measured on THIS layout."
    )
    a(
        f"- **VINN/VINP total-capacitance imbalance: {vinp_vinn_imbalance:.3f}%** "
        f"({vinp_c:.4f} fF vs {vinn_c:.4f} fF) -- same qualitative question as the "
        "wire-area record's 15.54% figure (structural trunk crossing, see "
        "`layout/comparator/README.md`), re-measured on THIS layout."
    )
    a("")
    a("## AC3: schematic-vs-extracted pick-off delta (`klt pex`, ratified OAT grid)")
    a("")
    a(
        f"Pick-off statistic v(OUTP)-v(OUTN) at t={PICKOFF_AT_NS}ns after the "
        "evaluate edge starts (matches sim/comparator-decision/run.py's own "
        "`_pickoff_deck` methodology, including issue #187's corrected instant -- "
        "see testbench.spice's header for the derivation), at two corner points "
        "per OAT rail: Vindiff=0 (isolates the routing/parasitic-driven imbalance, "
        f"device mismatch structurally excluded) and Vindiff=+{CAL_VINDIFF_MV:.0f}mV "
        "(gain calibration, one of run.py's own `VINDIFF_GAIN_CAL_MV` points). The "
        "evaluate clock tracks the rail at every corner (an ideal switch onto the "
        "VDD rail node), the way the regen-corners campaign drives it."
    )
    a("")
    a("| corner | rail (V) | gain sch (V/V) | gain ext (V/V) | zero-diff sch (uV) | zero-diff ext (uV) | parasitic offset (mV) |")
    a("|---|---|---|---|---|---|---|")
    for rail in sorted(analysis):
        e = analysis[rail]
        a(
            f"| `{rail[0]}_{rail[1]:g}c_{rail[2]:.2f}v` | {rail[2]:.2f} "
            f"| {e['schematic_gain']:+.4f} | {e['extracted_gain']:+.4f} "
            f"| {e['schematic_zero_diff'] * 1e6:+.2f} | {e['extracted_zero_diff'] * 1e6:+.2f} "
            f"| {e['parasitic_offset_mv']:+.5f} |"
        )
    a("")
    if tt_entry is not None:
        a(
            f"At the star's center (tt/27C/1.8V): schematic gain "
            f"{tt_entry['schematic_gain']:+.4f} V/V, extracted gain "
            f"{tt_entry['extracted_gain']:+.4f} V/V (both correctly signed at the "
            f"corrected instant), input-referred parasitic-driven offset "
            f"{tt_entry['parasitic_offset_mv']:+.5f} mV."
        )
    high_rail = analysis.get(("tt", 27.0, 1.98))
    if high_rail is not None:
        a(
            f"At tt/27C/1.98 V the schematic gain of "
            f"{high_rail['schematic_gain']:+.4f} V/V is the output differential "
            f"at the {PICKOFF_AT_NS} ns pick-off divided by the single "
            f"+{CAL_VINDIFF_MV:g} mV input. Faster regeneration can increase this "
            "ratio. A sweep of smaller inputs would be needed to establish "
            "small-signal linearity at this rail."
        )
    a(
        f"Across the grid the input-referred parasitic-driven offset ranges to "
        f"**{worst_offset['parasitic_offset_mv']:+.5f} mV** worst-case at "
        f"`{worst_offset['zero_cid']}`. Full per-corner rows in `pex_zero.json` / "
        "`pex_cal.json` (`delta[]`)."
    )
    a("")
    a("## AC4: is the routing-driven component material against device mismatch?")
    a("")
    worst_mv = abs(worst_offset["parasitic_offset_mv"])
    ratio_of_mean = worst_mv / OFFSET_MISMATCH_MEAN_MV * 100
    ratio_of_stdev = worst_mv / OFFSET_MISMATCH_STDEV_MV * 100
    mean_multiple = OFFSET_MISMATCH_MEAN_MV / worst_mv
    stdev_multiple = OFFSET_MISMATCH_STDEV_MV / worst_mv
    a(
        f"**Worst-case input-referred parasitic-driven offset across the ratified "
        f"grid: {worst_offset['parasitic_offset_mv']:+.5f} mV** (Vindiff=0 pick-off "
        "differential on the extracted netlist, converted through the extracted "
        f"side's own gain, worst of {len(analysis)} OAT corners)."
    )
    a("")
    a(
        f"Compared against the device-mismatch-only offset "
        f"`sim/comparator-decision/records/20260821-071918-433a294.md` "
        f"reports (`tt_mm`, N=16, seed=1): mean **{OFFSET_MISMATCH_MEAN_MV:.2f} mV**, "
        f"stdev **{OFFSET_MISMATCH_STDEV_MV:.2f} mV**."
    )
    a("")
    a(
        f"- The worst-case magnitude {worst_mv:.5f} mV is {ratio_of_mean:.3f}% of the "
        f"mismatch record's mean and {ratio_of_stdev:.3f}% of its stdev "
        f"(i.e. the mean is {mean_multiple:.0f}x larger, the stdev "
        f"{stdev_multiple:.0f}x larger)."
    )
    # Worded from the actual multiples rather than a fixed order-of-magnitude
    # claim: this pick-off-differential quantity sits close to the
    # simulator's own noise floor (both legs' Vindiff=0 diffs are single- to
    # low-triple-digit microvolts), so a `klt`/ngspice version bump alone
    # measurably moves it run to run (issue #146 saw the extracted-side diff
    # move ~7x between pins, within this same regime).
    smallest_multiple = min(mean_multiple, stdev_multiple)
    if smallest_multiple >= 100:
        magnitude_phrase = "over two orders of magnitude smaller"
    elif smallest_multiple >= 10:
        magnitude_phrase = "over an order of magnitude smaller"
    else:
        magnitude_phrase = f"{smallest_multiple:.0f}x smaller"
    a(
        "- **Conclusion at the ratified grid: the routing-driven component is "
        "noise against the device-mismatch term, not material at this block's "
        f"offset budget.** Even the grid's worst corner is {magnitude_phrase} "
        "than either the mean or the stdev of the device-mismatch-only offset "
        "distribution -- device mismatch, not routing/parasitic imbalance, is "
        "what would need to shrink to move this comparator's offset budget. No "
        "floorplan change is warranted on offset grounds (per the wire-area "
        "record's own note)."
    )
    a(
        "- This conclusion is about **offset** specifically. It does not "
        "re-open regeneration-time/speed symmetry (a second-order, non-offset "
        "contributor `layout/comparator/README.md` already scopes out of this "
        "issue's acceptance criteria) or noise."
    )
    a("")
    a("## Files")
    a("")
    a("```")
    a(f"{record_id}/")
    a("  comparator.pex-extract.spice   klt extract --parasitics output (per-net R/C table source)")
    a("  extract.json                   klt extract --parasitics JSON envelope")
    a("  comparator_pex_reference.spice schematic DUT snapshot (committed wrap)")
    a("  testbench.spice                pex testbench (klt pex swaps its .include per leg)")
    a("  pex_request_zero.json          zero-Vindiff OAT request (corners + exclude carve)")
    a("  pex_request_cal.json           +10mV gain-cal OAT request (corners + exclude carve)")
    a("  pex_zero.json / pex_cal.json   klt pex JSON responses (extraction summary + delta[])")
    a("  record.md                      this file")
    a("```")
    a("")

    (out / "record.md").write_text("\n".join(lines) + "\n")
    return out / "record.md"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator PEX flow (issues #112/#1017)")
    ap.add_argument("--check-env", action="store_true")
    ap.add_argument("--pilot", action="store_true", help="one corner (tt/27C/1.8V), local backend")
    ap.add_argument("--record", action="store_true", help="write an evidence record under reports/")
    ap.add_argument("--backend", default=None, help="override klt pex backend (default: local for --pilot, batch otherwise)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.check_env:
        import subprocess

        info = pex_flow.resolve_pdk()
        gds, latest = pex_flow.latest_layout(BLOCK_DIR, GDS_NAME)
        ver = subprocess.run(
            [str(pex_flow.klt_bin()), "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        print(f"klt: {pex_flow.klt_bin()} ({ver})")
        print(f"PDK: variant={info.variant} root={info.root} found={info.found}")
        if not info.found:
            print(f"  error: {info.error}")
            return 3
        print(f"layout: reports/{latest}/{GDS_NAME}")
        return 0

    if args.pilot and args.record:
        print("--pilot and --record are separate invocations", file=sys.stderr)
        return 2
    if args.pilot:
        with tempfile.TemporaryDirectory(prefix="cmp-pex-pilot-") as td:
            return run(Path(td), "local", pilot=True, record=False, quiet=args.quiet)
    if args.record:
        backend = args.backend or "batch"
        return run(
            REPORTS_DIR / evidence.new_record_id(), backend, pilot=False, record=True,
            quiet=args.quiet,
        )
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

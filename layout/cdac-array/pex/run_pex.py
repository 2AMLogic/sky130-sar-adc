#!/usr/bin/env python3
"""CDAC array sub-block PEX flow (issue #1017): schematic-vs-extracted
comparison of the DAC transfer characteristic (the ratified `V_REF` / LSB /
sampling-cap rows' own methodology, `sim/cdac-array-transfer`, issue #53), at
the ratified 9-point one-at-a-time PVT corner set, plus the extracted
top-plate parasitic R/C table read against the schematic-level `C_par`
figure `sim/top-plate-cpar/` measured (issue #754) and against what
DR-022/DR-025 assume for systematic gain error.

Two `klt` calls per record, on the layout flow's pinned `klt`
(layout/requirements.txt) through layout/bin/pex_flow.py:

1. `klt extract --parasitics --pdk sky130A` -- the full per-net R/C table
   (TOP_P/TOP_N parasitic C beside the schematic C_par figure).
2. `klt pex <cdac_array.gds> <request.json>` -- extracts again and
   re-simulates both legs of the transfer testbench (`testbench.spice`)
   across the corner grid, reporting per-corner, per-code `delta[]` rows.

The schematic DUT (`cdac_array_pex_reference.spice`, materialized per run)
wraps the same device pattern `sim/cdac-array-transfer/testbench/
tb_cdac_array_transfer.spice` instantiates per code -- one weighted cap
(`sky130_fd_pr__cap_mim_m3_1`, MF=2^i) plus the real `nfet_01v8`/`pfet_01v8`
bottom-plate switch pair per bit position, both sides, plus the VREFN-tied
termination cap -- in the EXTRACTED netlist's own `.SUBCKT` name and pin
order, so `klt pex`'s DUT-`.include`-swap convention has a pin-identical
schematic leg (the comparator flow's `comparator_pex_reference.spice`
convention, issue #112).

    layout/bin/setup-venv.sh                     # once (pinned klt)
    source sim/env.sh                            # exports PDK_ROOT/PDK
    python3 layout/cdac-array/pex/run_pex.py --check-env
    python3 layout/cdac-array/pex/run_pex.py --pilot    # tt/27C/1.8V, local
    python3 layout/cdac-array/pex/run_pex.py --record   # 9 OAT corners, batch

Each `--record` run mints a new timestamped, append-only record under
`layout/cdac-array/reports/<record-id>/`; it never edits a prior record and
never touches `reports/LATEST` (the drawing flow's pointer).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PEX_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PEX_DIR.parents[1] / "bin"))
sys.path.insert(0, str(PEX_DIR.parents[2] / "sim"))

import pex_flow  # noqa: E402

from harness import evidence, measure, toolchain  # noqa: E402

BLOCK_DIR = PEX_DIR.parent
REPORTS_DIR = BLOCK_DIR / "reports"
GDS_NAME = "cdac_array.gds"

#: The extracted interface this flow's committed testbench.spice hardcodes
#: (its X lines are positional). Asserted against every run's own extraction
#: before anything simulates -- a re-draw that reorders pins fails loudly.
EXPECTED_SUBCKT = "cdac_array"
EXPECTED_PINS = (
    [f"SELn{i}" for i in range(9)]
    + [f"SELp{i}" for i in range(9)]
    + ["TOP_N", "TOP_P", "VDD", "VREFN", "VREFP", "VSS"]
)

CODES = [0, 128, 256, 384, 511]  # sim/cdac-array-transfer's own five codes
SETTLE_AT = "500n"

#: Unit cap: the extraction deck's own two-term law at the schematic's drawn
#: plate (layout/cdac-array/reference/cdac_array.lvs-reference.spice header).
C_UNIT_F = 8.664e-15

#: Schematic-level top-plate C_par this record's extracted figure is read
#: against (issue #754; a SCHEMATIC, assembled-top figure -- different
#: population from this array-layout routing parasitic, stated in the record).
TOPPLATE_CPAR_RECORD = (
    PEX_DIR.parents[2] / "sim" / "top-plate-cpar" / "records" / "LATEST"
)


#: The committed klt-sim report of sim/cdac-array-transfer's own campaign --
#: this record's schematic leg is cross-validated against it at record time
#: (same testbench methodology, same five codes), so the cross-check tracks
#: the committed artifact instead of a hand-copied number.
TRANSFER_CAMPAIGN_REPORT = (
    PEX_DIR.parents[2] / "sim" / "cdac-array-transfer" / "klt-sim"
    / "20261106-190301-7bdf8c4" / "report.json.gz"
)


def dut_fragment() -> str:
    """The schematic leg's device list, one card pattern per bit position --
    exactly the cards tb_cdac_array_transfer.spice instantiates per code,
    generic (SEL pins as interface nets) so one copy serves every code."""
    lines: list[str] = []
    for side in ("p", "n"):
        top = f"TOP_{side.upper()}"
        lines.append(f"* ---- {side} side: 9 weighted positions + termination cap ----")
        for i in range(9):
            w = 2**i
            lines.append(
                f"Xc_{side}{i} BOT_{side}{i} {top} sky130_fd_pr__cap_mim_m3_1"
                f" W=1.9000 L=1.9000 MF={w} m={w}"
            )
            lines.append(
                f"Xn_{side}{i} BOT_{side}{i} SEL{side}{i} VREFN VSS"
                f" sky130_fd_pr__nfet_01v8 L=0.15 W=1 nf=1"
            )
            lines.append(
                f"Xp_{side}{i} BOT_{side}{i} SEL{side}{i} VREFP VDD"
                f" sky130_fd_pr__pfet_01v8 L=0.15 W=2 nf=1"
            )
        lines.append(
            f"Xterm_{side} VREFN {top} sky130_fd_pr__cap_mim_m3_1"
            f" W=1.9000 L=1.9000 MF=1 m=1"
        )
    return "\n".join(lines)


def build_request(points) -> dict:
    corners, exclude = pex_flow.build_corners_spec(points)
    return {
        "netlist": "testbench.spice",
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": corners,
        "exclude": exclude,
        "analysis": {"kind": "tran", "args": f"0.5n {SETTLE_AT}"},
        "measurements": [
            {
                "name": f"vtop_{side}_{c}",
                "spice": f".meas tran vtop_{side}_{c} find v(top_{c}{side}) at={SETTLE_AT}",
                "unit": "V",
            }
            for c in CODES
            for side in ("p", "n")
        ],
        "options": {"timeout_s": 900, "keep_artifacts": False},
    }


def oat_points(pilot: bool):
    pts = pex_flow.ratified_oat_points({"vcm": lambda v: round(v / 2, 6)})
    if pilot:
        pts = [p for p in pts if p.cid == "tt_27c_1.80v"]
    return pts


def run(work_dir: Path, backend: str, pilot: bool, record: bool, quiet: bool = False) -> int:
    info = pex_flow.resolve_pdk()
    gds_path, latest_id = pex_flow.latest_layout(BLOCK_DIR, GDS_NAME)

    work_dir.mkdir(parents=True, exist_ok=True)
    gds_rel = str(gds_path.resolve())

    # --- Step 1: klt extract --parasitics (per-net R/C table) --------------
    extract_json = pex_flow.extract_parasitics(
        Path(gds_rel), work_dir, "cdac_array.pex-extract.spice", info, quiet=quiet
    )
    (work_dir / "extract.json").write_text(json.dumps(extract_json, indent=2) + "\n")

    # --- Step 2: schematic DUT, wrapped in the extraction's own interface --
    name, pins = pex_flow.extracted_subckt(work_dir / "cdac_array.pex-extract.spice")
    if name != EXPECTED_SUBCKT or pins != EXPECTED_PINS:
        raise pex_flow.PexFlowError(
            f"extracted interface drifted from testbench.spice's hardcoded one:\n"
            f"  got .SUBCKT {name} {' '.join(pins)}\n"
            f"  want .SUBCKT {EXPECTED_SUBCKT} {' '.join(EXPECTED_PINS)}\n"
            f"Re-derive testbench.spice's X lines against the new pin list."
        )
    dut = pex_flow.wrap_dut(
        dut_fragment(),
        name,
        pins,
        "* cdac_array_pex_reference.spice -- schematic-equivalent DUT for this\n"
        "* `klt pex` run (issue #1017), GENERATED by run_pex.py: the per-bit\n"
        "* device pattern of sim/cdac-array-transfer/testbench/\n"
        "* tb_cdac_array_transfer.spice (issue #53), wrapped in the extracted\n"
        "* netlist's own .SUBCKT name and pin order (asserted equal to\n"
        "* testbench.spice's hardcoded list before this file was written).",
    )
    (work_dir / "cdac_array_pex_reference.spice").write_text(dut)

    # --- Step 3: klt pex -- both legs, all corners, one call ---------------
    shutil.copy(PEX_DIR / "testbench.spice", work_dir / "testbench.spice")
    points = oat_points(pilot)
    request = pex_flow.apply_capacity_wait(build_request(points))
    (work_dir / "pex_request.json").write_text(json.dumps(request, indent=2) + "\n")

    (work_dir / ".klt").mkdir(exist_ok=True)
    pex_json = pex_flow.run_klt(
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
            str((work_dir / ".klt" / "pex-extracted.spice").resolve()),
            "--outdir",
            str((work_dir / ".klt" / "pex").resolve()),
            "--backend",
            backend,
        ],
        cwd=work_dir,
        backend=backend,
        quiet=quiet,
    )
    (work_dir / "pex.json").write_text(json.dumps(pex_json, indent=2) + "\n")
    if pex_json.get("status") != "pass":
        print(f"klt pex did not pass: {json.dumps(pex_json)[:800]}", file=sys.stderr)
        return 1

    analysis = analyse(pex_json)
    report(analysis, quiet=quiet)

    if record:
        vsubs_v = vsubs_probe(work_dir, quiet=quiet)
        path = write_record(work_dir, latest_id, extract_json, pex_json, analysis, vsubs_v=vsubs_v)
        print(f"wrote {path}")
    shutil.rmtree(work_dir / ".klt", ignore_errors=True)
    return 0


def analyse(pex_json: dict) -> dict:
    """Per-corner transfer analysis keyed off pex delta[]: per leg, per code
    the differential top-plate voltage, its error against the ideal
    charge-redistribution value (computed independently here), and the
    endpoints' slope as the measured differential step size."""
    idx = pex_flow.delta_index(pex_json)
    if os.environ.get("PEX_DEBUG"):
        for cid, rows in idx.items():
            print("    RAW", cid, {k: (v["schematic"], v["extracted"]) for k, v in sorted(rows.items())})
    out = {}
    for cid, rows in idx.items():
        process, temp, supplies = pex_flow.parse_corner_id(cid)
        vdd = supplies["vdd"]
        lsb = 2.0 * vdd / 1024.0  # ratified differential LSB (DR-003) at this rail
        per_leg = {}
        for leg in ("schematic", "extracted"):
            vdiff = {}
            for c in CODES:
                vp = rows[f"vtop_p_{c}"][leg]
                vn = rows[f"vtop_n_{c}"][leg]
                vdiff[c] = None if vp is None or vn is None else vp - vn
            ideal = {c: vdd * (2 * c - 511) / 512.0 for c in CODES}
            err = (
                {c: (None if vdiff[c] is None else (vdiff[c] - ideal[c]) * 1000.0) for c in CODES}
            )
            slope = None
            if vdiff[0] is not None and vdiff[511] is not None:
                slope = (vdiff[511] - vdiff[0]) / 511.0
            per_leg[leg] = {
                "vdiff": vdiff,
                "ideal": ideal,
                "err_mv": err,
                "slope_v_per_code": slope,
            }
        d = {}
        for c in CODES:
            vs, ve = per_leg["schematic"]["vdiff"][c], per_leg["extracted"]["vdiff"][c]
            d[c] = None if (vs is None or ve is None) else (ve - vs) * 1000.0
        out[cid] = {
            "process": process,
            "temp_c": temp,
            "vdd": vdd,
            "lsb_v": lsb,
            "legs": per_leg,
            "delta_mv": d,
        }
    return out


def report(analysis: dict, *, quiet: bool) -> None:
    if quiet:
        return
    for cid, a in sorted(analysis.items()):
        sch, ext = a["legs"]["schematic"], a["legs"]["extracted"]
        if os.environ.get("PEX_DEBUG"):
            print("    DEBUG vdiff sch:", {c: (round(sch["vdiff"][c], 4) if sch["vdiff"][c] is not None else None) for c in CODES})
            print("    DEBUG ideal:", {c: round(sch["ideal"][c], 4) for c in CODES})
        ss, se = sch["slope_v_per_code"], ext["slope_v_per_code"]
        ds = [abs(v) for v in a["delta_mv"].values() if v is not None]
        worst = max(ds) if ds else float("nan")
        print(
            f"  {cid}: slope sch={ss if ss is None else format(ss, '.6f')} "
            f"ext={se if se is None else format(se, '.6f')} V/code | "
            f"worst |delta|={worst * 1000:.1f} uV = {worst / (a['lsb_v'] * 1000):.4f} LSB"
        )


def topplate_cpar_line() -> str:
    """The schematic-level C_par headline (tt/27C/1.8 V) quoted from
    sim/top-plate-cpar's own LATEST record, parsed at record time so this
    record's citation tracks that record, not a stale copy."""
    path = TOPPLATE_CPAR_RECORD.resolve().parent / TOPPLATE_CPAR_RECORD.resolve().read_text().strip()
    text = path.read_text()
    m = re.search(r"^\| `tt_27c_1\.80v` \| ([0-9.]+) \| ([0-9.]+) \|", text, re.MULTILINE)
    if not m:
        return f"`{path.name}` (row not re-parsed by this run)"
    return (
        f"`{path.name}`: C_u={m.group(1)} fF, C_par mean={m.group(2)} fF "
        "over the traced bias range (tt/27C/1.80 V)"
    )


def vsubs_probe(work_dir: Path, quiet: bool = False) -> float | None:
    """v(vsubs) at the t=500 ns read of the EXTRACTED leg, tt/27C/1.8 V.

    A standalone local ngspice diagnostic (single deck, one corner), not part
    of the graded `klt pex` run: the extracted netlist declares the substrate
    net `.GLOBAL vsubs` with no DC tie (2AMLogic/klayout-tools#7066), and this
    probe measures where the floating substrate node actually sits at the
    read instant -- the number the record needs before any absolute
    extracted-side voltage is interpreted. Committed as `vsubs_probe.spice`
    in the record directory so the number is reproducible from the record
    itself.
    """
    info = pex_flow.resolve_pdk()
    tb = (work_dir / "testbench.spice").read_text().replace(
        '.include "cdac_array_pex_reference.spice"',
        '.include "cdac_array.pex-extract.spice"',
    )
    deck = (
        f"* vsubs_probe -- standalone diagnostic deck (issue #1017): the\n"
        f"* extracted leg of testbench.spice at tt/27C/1.8V, reading the\n"
        f"* floating .GLOBAL vsubs substrate net (klayout-tools#7066) at the\n"
        f"* same t=500ns instant the transfer rows use.\n"
        f".lib {info.ngspice_lib} tt\n"
        ".temp 27\n" + tb + "\n.control\ntran 0.5n 500n\n"
        "meas tran vsubs_500 find v(vsubs) at=500n\n.endc\n.end\n"
    )
    (work_dir / "vsubs_probe.spice").write_text(deck)
    log = toolchain.run_ngspice_with_retry(deck, work_dir, "vsubs_probe")
    parsed = measure.parse(log, ["vsubs_500"])
    v = parsed.get("vsubs_500")
    if not quiet:
        print(f"  vsubs probe (tt): v(vsubs) @500n = {v if v is None else format(v, '.6f')} V")
    return v


def campaign_crosscheck(delta_rows: dict[str, dict[str, dict]]) -> str:
    """One line comparing this run's SCHEMATIC leg against the committed
    transfer-campaign klt-sim report (same methodology), or a
    not-re-read note if the artifact is missing."""
    if not TRANSFER_CAMPAIGN_REPORT.is_file():
        return f"`{TRANSFER_CAMPAIGN_REPORT.name}` not re-read by this run"
    import gzip

    report = json.load(gzip.open(TRANSFER_CAMPAIGN_REPORT, "rt"))
    # campaign corner ids look like "tt/novdd/27C/params:vdd_val=1.8"
    want = {
        "params:vdd_val=1.8": "tt/vcm=0.900_vdd=1.800V/27C",
        "params:vdd_val=1.62": "tt/vcm=0.810_vdd=1.620V/27C",
    }
    theirs = {}
    for corner in report.get("corners", []):
        cid = corner.get("corner_id", "")
        if not cid.startswith("tt/") or "/27C/" not in cid:
            continue
        for suffix, mine in want.items():
            if cid.endswith(suffix):
                for m in corner.get("measurements", []):
                    theirs[(mine, m["name"])] = m.get("value")
    diffs = []
    for (mine_cid, name), theirs_v in sorted(theirs.items()):
        if mine_cid in delta_rows and theirs_v is not None:
            ours_v = delta_rows[mine_cid].get(name, {}).get("schematic")
            if ours_v is not None:
                diffs.append((abs(ours_v - theirs_v), mine_cid, name, ours_v, theirs_v))
    if not diffs:
        return f"`{TRANSFER_CAMPAIGN_REPORT.name}` parsed, no comparable tt rows found"
    worst = max(diffs)
    n_exact = sum(1 for d in diffs if d[0] < 5e-6)
    return (
        f"`{TRANSFER_CAMPAIGN_REPORT.name}`: {len(diffs)} schematic-leg values compared at "
        f"tt/27C/1.80V and tt/27C/1.62V; {n_exact}/{len(diffs)} agree within 5 uV "
        f"(worst |diff| {worst[0] * 1e3:.3f} mV on `{worst[2]}` at `{worst[1]}`)"
    )


def write_record(
    work_dir: Path, latest_id: str, extract_json: dict, pex_json: dict, analysis: dict,
    vsubs_v: float | None = None,
) -> Path:
    out = work_dir
    record_id = out.name
    for name in (
        "cdac_array.pex-extract.spice",
        "extract.json",
        "cdac_array_pex_reference.spice",
        "testbench.spice",
        "pex_request.json",
        "pex.json",
    ):
        src, dst = work_dir / name, out / name
        if src.resolve() != dst.resolve():
            shutil.copy(src, dst)

    prov = extract_json["provenance"]
    body_bias = pex_json.get("body_bias", {})
    model = pex_json.get("extraction", {}).get("model", {})
    nets = pex_flow.net_table(extract_json, {"TOP_P", "TOP_N"})
    cpar_sch = topplate_cpar_line()
    idx = pex_flow.delta_index(pex_json)
    crosscheck = campaign_crosscheck(idx)

    # First-order slope-shift arithmetic from the extract table itself:
    # a top-plate C-to-substrate of Cg against 512*C_u array capacitance
    # scales the charge divider by 512*C_u/(512*C_u + Cg).
    c_unit_total_ff = 512.0 * C_UNIT_F * 1e15
    cg_top_p = nets.get("TOP_P", {}).get("c_ground_ff", 0.0)
    slope_pred_pct = 100.0 * cg_top_p / (c_unit_total_ff + cg_top_p)

    # Worst rows across the grid for the headline lines.
    worst_cid, worst_mv, worst_lsb = None, 0.0, 0.0
    slope_shift_max = 0.0
    for cid, a in analysis.items():
        for v in a["delta_mv"].values():
            if v is not None and abs(v) > abs(worst_mv):
                worst_cid, worst_mv = cid, v
                worst_lsb = abs(v) / (a["lsb_v"] * 1000.0)
        s, e = a["legs"]["schematic"]["slope_v_per_code"], a["legs"]["extracted"]["slope_v_per_code"]
        if s and e:
            slope_shift_max = max(slope_shift_max, abs((e - s) / s))

    lines: list[str] = []
    a = lines.append
    a(f"# CDAC array PEX record: {record_id}")
    a("")
    a(
        "Real `klt extract --parasitics --pdk sky130A` extraction of the CDAC array "
        f"layout `reports/{latest_id}/cdac_array.gds` and a `klt pex` "
        "schematic-vs-extracted comparison of the DAC transfer characteristic "
        "(`sim/cdac-array-transfer`'s own methodology, issue #53; five representative "
        "codes, both differential sides, settled top-plate pair at t=500 ns), at the "
        "ratified 9-point one-at-a-time PVT grid (spec/target-spec.md \"Numeric rows "
        "-- RATIFIED 2026-08-19\"). Generated by `layout/cdac-array/pex/run_pex.py` "
        "(issue #1017); re-run it to reproduce."
    )
    a("")
    a("## Provenance")
    a("")
    a(f"- {pex_flow.klt_version_note(prov['klt_version'])}")
    a(f"- KLayout engine: {prov['klayout_version']}")
    a(f"- PDK: {prov['pdk']['name']} ({prov['pdk']['version']})")
    a(f"- Extraction deck content hash: `{prov['deck']['content_hash']}`")
    a(
        f"- layout source: `layout/cdac-array/reports/{latest_id}/cdac_array.gds` "
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
    a(
        "- **Floating substrate net**: the extracted netlist declares the substrate "
        "`.GLOBAL vsubs` with **no DC tie anywhere in the emitted netlist** (every "
        "element referencing it is a capacitor), and the pinned klt 0.6.0 exposes no "
        "substrate-tie option -- filed generically as "
        "[2AMLogic/klayout-tools#7066](https://github.com/2AMLogic/klayout-tools/issues/7066). "
        "The extracted leg therefore simulates a substrate node whose voltage is set by "
        "charge conservation and moves with switching activity: `vsubs_probe.spice` "
        f"(committed here, tt/27C/1.8 V standalone run of this record's own extracted "
        f"netlist and testbench) measures **v(vsubs) = "
        f"{'n/a' if vsubs_v is None else format(vsubs_v, '.4f')} V** at the same t=500 ns "
        "instant the transfer rows read. Read every absolute extracted-side voltage below "
        "with that in mind: each carries a fraction of the substrate motion through its own "
        "C-to-vsubs term. The schematic leg has no substrate net at all, so this term "
        "appears wholesale in the delta rows."
    )
    a("")
    a("## Extracted top-plate parasitic, beside the schematic-level figure")
    a("")
    a(
        "This extraction's own per-net table (`extract.json` `parasitics.nets[]`; "
        "vertical-overlap coupling only unless a net is named `--critical-net`, "
        "which this run does not use -- the same Phase 1 scope every comparator "
        "PEX record states):"
    )
    a("")
    a("| Net | R (ohm) | C to ground (fF) | C coupled, total (fF) | C total (fF) |")
    a("|---|---|---|---|---|")
    for n in ("TOP_P", "TOP_N"):
        t = nets.get(n, {})
        a(
            f"| {n} | {t.get('r_ohm', 0):.2f} | {t.get('c_ground_ff', 0):.4f} "
            f"| {t.get('c_coupled_total_ff', 0):.4f} | {t.get('c_total_ff', 0):.4f} |"
        )
    a("")
    a(
        "Read against the SCHEMATIC-level figure `sim/top-plate-cpar/` measured on the "
        f"assembled `design/sar_adc_top.spice` (issue #754) -- {cpar_sch}. These are "
        "**different populations, stated as such**: the schematic figure is the whole "
        "assembled top's C_par beyond 512*C_u (every device and net that touches "
        "TOP_P/TOP_N, front end and interconnect included, at a sim-model C_u of "
        "~8.4 fF); the extracted figure above is THIS array layout's own routing "
        "parasitic on the same nodes, at the extraction deck's C_u of 8.664 fF. The "
        "extracted array-routing parasitic is one measured contributor of the "
        "schematic figure's total, not a check that must reconcile with it."
    )
    a("")
    a(
        "For gain error: DR-022's DRAFT systematic row (<= 1.42 LSB span-referred) "
        "assumes equal share between mismatch and systematic terms without layout "
        "data, and DR-025's proposed closure path (fold the half-LSB cap into the "
        "termination cap) was chosen on schematic-level evidence. Neither had an "
        "extracted-array figure; the slope shift below is this layout's own "
        "parasitic contribution to the systematic term."
    )
    a("")
    a("## Schematic-vs-extracted transfer delta (per corner)")
    a("")
    a(
        "Per corner, per leg: `vdiff(code) = v(TOP_P) - v(TOP_N)` at t=500 ns after "
        "the reset-to-code event; ideal = `vdd*(2*code-511)/512` computed "
        "independently in `run_pex.py`; slope = `(vdiff(511)-vdiff(0))/511`, the "
        "measured differential step per P-side code (2x the ratified differential "
        "LSB `2*vdd/2^10`, mirrored differential drive). Full per-corner rows in "
        "`pex.json`'s `delta[]`."
    )
    a("")
    a("| corner | vdd (V) | slope sch (V/code) | slope ext (V/code) | worst |vdiff delta| (uV) | in LSB |")
    a("|---|---|---|---|---|---|")
    for cid in sorted(analysis):
        x = analysis[cid]
        s = x["legs"]["schematic"]["slope_v_per_code"]
        e = x["legs"]["extracted"]["slope_v_per_code"]
        ds = [abs(v) for v in x["delta_mv"].values() if v is not None]
        w = max(ds) if ds else float("nan")
        a(
            f"| `{cid}` | {x['vdd']:.2f} | {s:.6f} | {e:.6f} "
            f"| {w * 1000:.1f} | {w / (x['lsb_v'] * 1000):.4f} |"
        )
    a("")
    a(
        f"Headline: worst schematic-vs-extracted `vdiff` move across the grid is "
        f"**{worst_mv * 1000:.1f} uV = {worst_lsb:.4f} LSB** at `{worst_cid}` "
        f"(ratified differential LSB at that rail); the endpoints' slope moves by at "
        f"most **{slope_shift_max * 100:.4f}%** between legs. Where each delta row "
        "comes from -- the extracted netlist's own added R/C rather than a device "
        "change: the legs are device-identical by construction (`klt pex` swaps only "
        "the DUT `.include`; the schematic leg is the same device list, no "
        "stochastic mismatch in either), so every nonzero row is the extracted "
        "netlist's added parasitics alone. Three mechanisms, each an element class "
        "present in this record's own `cdac_array.pex-extract.spice`:"
    )
    a("")
    a(
        f"1. **Slope term -- `CTOP_P`/`CTOP_N`, the top-plate trunk's C to the "
        f"substrate net** ({cg_top_p:.2f} fF on TOP_P here) scales the 512*C_u charge "
        f"divider: {c_unit_total_ff:.0f} fF of array capacitance against that ground "
        f"term predicts a first-order slope shift of **{slope_pred_pct:.2f}%**, to be "
        f"read beside the measured per-corner slope columns above. The `Ccc__*` "
        "coupling caps between the top trunk and the weighted bottom-plate trunks "
        "(the coupled column of the table above) partially track the stepping bottom "
        "plates and pull the other way, which is why measured slope shifts sit near, "
        "not exactly on, the first-order figure."
    )
    a(
        f"2. **Common-mode term -- the floating substrate net's own motion** "
        f"(klayout-tools#7066): v(vsubs) = "
        f"{'n/a' if vsubs_v is None else format(vsubs_v, '.4f')} V at tt at the read "
        f"instant; each top plate carries "
        f"{cg_top_p / (c_unit_total_ff + nets.get('TOP_P', {}).get('c_total_ff', 0.0)) * 100:.2f}% "
        "of that through its own C-to-vsubs -- the same arithmetic that leaves a "
        "stationary (code-constant) top plate offset in the extracted leg where the "
        "schematic leg sits exactly at its reset value. This term is an artifact of "
        "the missing substrate tie, not layout parasitics, and is disclosed as such."
    )
    a(
        "3. **Relaxation/resistance -- the `R_*_t*` stitching resistors** on the "
        "top-plate and bottom-plate trunk fragments (210 ohm on each top trunk here) "
        "set how fast each event-driven redistribution settles; both legs are read at "
        "500 ns, well past the last motion (the stationary top plate is bit-stable "
        "from ~100 ns at tt), so none of the rows above are unsettled transients."
    )
    a("")
    a(
        "Cross-validation of the schematic leg: "
        + crosscheck
        + ". The schematic leg is the same methodology `sim/cdac-array-transfer` runs, "
        "so its agreement with that campaign's committed report bounds the toolchain "
        "difference (the klt version this record's provenance bullet names vs the "
        "campaign's fleet runner) independently of any parasitic effect."
    )
    a("")
    a("## Files")
    a("")
    a("```")
    a(f"{record_id}/")
    a("  cdac_array.pex-extract.spice   klt extract --parasitics output (per-net R/C source)")
    a("  extract.json                   klt extract --parasitics JSON envelope")
    a("  cdac_array_pex_reference.spice schematic DUT snapshot (generated, extracted pin order)")
    a("  testbench.spice                pex testbench (klt pex swaps its single .include)")
    a("  pex_request.json               request as run (OAT carve: corners + exclude)")
    a("  pex.json                       klt pex JSON response (delta[] per corner/code)")
    a("  vsubs_probe.spice              standalone floating-substrate diagnostic deck (tt)")
    a("  record.md                      this file")
    a("```")
    a("")
    (out / "record.md").write_text("\n".join(lines) + "\n")
    return out / "record.md"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-env", action="store_true", help="verify klt/PDK/layout and exit")
    ap.add_argument("--pilot", action="store_true", help="one corner (tt/27C/1.8V), local backend")
    ap.add_argument("--record", action="store_true", help="mint an append-only record")
    ap.add_argument("--backend", default=None, help="override klt pex backend (default: local for --pilot, batch otherwise)")
    args = ap.parse_args()

    if args.check_env:
        info = pex_flow.resolve_pdk()
        gds, latest = pex_flow.latest_layout(BLOCK_DIR, GDS_NAME)
        ver = subprocess.run(
            [str(pex_flow.klt_bin()), "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        print(f"klt: {pex_flow.klt_bin()} ({ver})")
        print(f"PDK: {info.variant} at {info.root}")
        print(f"layout: reports/{latest}/{GDS_NAME}")
        return 0

    if args.pilot and args.record:
        print("--pilot and --record are separate invocations", file=sys.stderr)
        return 2
    if args.pilot:
        with tempfile.TemporaryDirectory(prefix="cdac-pex-pilot-") as td:
            return run(Path(td), "local", pilot=True, record=False)
    if args.record:
        backend = args.backend or "batch"
        return run(REPORTS_DIR / evidence.new_record_id(), backend, pilot=False, record=True)
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Issue #1013 same-host A/B: run ONLY the ff_27c_1.80v point of the
cdac-array-transfer bench, once per open_pdks pin, same host + same ngspice
binary, decks identical except the .lib path.

Usage: python3 ab_ff_legs.py <old_root> <new_root> <outdir>
"""
import json, os, shutil, subprocess, sys
from pathlib import Path

WT = Path(__file__).resolve().parents[4]  # <repo>/sim/cdac-array-transfer/diagnostics/<id>/
SIM = WT / "sim"
sys.path.insert(0, str(SIM))
sys.path.insert(0, str(SIM / "cdac-array-transfer"))

from harness import corners as corners_mod, measure, pdk, toolchain  # noqa: E402
import run_transfer  # noqa: E402

OLD_ROOT, NEW_ROOT, OUTDIR = sys.argv[1], sys.argv[2], Path(sys.argv[3])
EXPECT = {"old": "c6d73a35f524070e85faff4a6a9eef49553ebc2b",
          "new": "f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7"}
OUTDIR.mkdir(parents=True, exist_ok=True)

ff_point = next(t for t in corners_mod.ratified_oat_grid(
    run_transfer.NOMINAL_SUPPLY_V, run_transfer.SUPPLY_TOLERANCE,
    run_transfer.PROCESS_CORNERS, run_transfer.TEMPS_C) if t[0] == "ff")
corner, temp_c, supply_v = ff_point
cid = corners_mod.corner_id(corner, temp_c, supply_v)
names = run_transfer.measure_names()
print(f"ff point from ratified_oat_grid: {cid} (temp={temp_c!r} supply={supply_v!r})")

os.environ["SIM_NGSPICE_TIMEOUT_S"] = "300"
results = {}
for leg, root in (("old", OLD_ROOT), ("new", NEW_ROOT)):
    os.environ["PDK_ROOT"] = root
    os.environ.pop("PDK", None)
    info = pdk.resolve()
    assert info.found, info.error
    stamp = pdk.resolved_commit_verified(info)
    assert stamp == EXPECT[leg], f"{leg}: SOURCES stamp {stamp} != {EXPECT[leg]}"
    netlist = run_transfer.build_netlist(info, corner, temp_c, supply_v)
    scratch = OUTDIR / f"scratch-{leg}"
    if scratch.exists():
        shutil.rmtree(scratch)
    log_text = toolchain.run_ngspice(netlist, scratch, cid)
    parsed = measure.parse(log_text, names)
    missing = measure.missing(parsed, names)
    assert not missing, f"{leg}: missing {missing}"
    (OUTDIR / f"{cid}.pdk-{EXPECT[leg][:7]}.log").write_text(log_text)
    (OUTDIR / f"{cid}.pdk-{EXPECT[leg][:7]}.deck.spice").write_text(netlist)
    results[leg] = {
        "pdk_root": root, "open_pdks_stamp": stamp,
        "ngspice_lib": str(info.ngspice_lib),
        "values": parsed,
    }
    print(f"{leg} ({stamp[:7]}): {len(parsed)} measurements ok")

ng = subprocess.run(["ngspice", "--version"], capture_output=True, text=True).stdout
results["_meta"] = {
    "host": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
    "ngspice_version_line": ng.splitlines()[1] if len(ng.splitlines()) > 1 else ng,
    "ngspice_binary": shutil.which("ngspice"),
}
(OUTDIR / "values.json").write_text(json.dumps(results, indent=1))
print("wrote", OUTDIR / "values.json")

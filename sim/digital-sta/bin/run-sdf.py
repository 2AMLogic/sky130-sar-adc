#!/usr/bin/env python3
"""Mint one append-only SDF run for the routed digital macros (issue #679):

    klt extract --parasitics --def-net-connections   routed GDS -> SPEF whose nets attach to the DEF's instance pins
    klt sta (request.spef + request.sdf)             post-route SDF, one per Liberty corner

and writes

    sim/digital-sta/runs/<id>/sdf/<macro>.<corner>.sdf   the SDF the functional re-run annotates
    sim/digital-sta/runs/<id>/<macro>.sdf-sta.json       the `klt sta` report (repo path prefix scrubbed)
    sim/digital-sta/runs/<id>/executed-requests/         the requests as run
    sim/digital-sta/runs/<id>/inputs.sha256              GDS / DEF / spec inputs and every SPEF
    sim/digital-sta/records/<id>-sdf.md                  the record

<id> = <UTC stamp>-<short HEAD>; an existing run is never touched. Needs the
pinned klt (signoff/requirements.txt), an `openroad` on PATH, and the PDK whose
revision the routed layout was minted under (open_pdks f6eeac7):

    PDK=sky130A PDK_ROOT=~/.ciel KLT=.venv-signoff/bin/klt python3 -I sim/digital-sta/bin/run-sdf.py

The P&R inputs are the `reports/LATEST` record of each macro.
"""
import datetime, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
KLT = os.environ.get("KLT", "klt")
PDK_ROOT = os.environ.get("PDK_ROOT")
MACROS = {"sar-sequencer": ("sar_sequencer", "sar-sequencer"), "top-glue": ("top_glue", "top-glue")}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, cwd=REPO, **kw)
    if r.returncode != 0:
        sys.exit(f"{' '.join(map(str, args))} failed rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout


def main():
    if not PDK_ROOT:
        sys.exit("set PDK_ROOT (dir holding sky130A, open_pdks f6eeac7)")
    cs = json.loads((HERE / "corner-set.json").read_text())
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + head
    out, rec = HERE / "runs" / rid, HERE / "records" / f"{rid}-sdf.md"
    if out.exists() or rec.exists():
        sys.exit(f"{rid} already exists; records are append-only")
    (out / "sdf").mkdir(parents=True)
    (out / "executed-requests").mkdir()
    scratch = Path(tempfile.mkdtemp(prefix="klt-sdf-"))
    inputs, rows, pnr = [], {}, {}
    for m, (top, d) in MACROS.items():
        rdir = REPO / "layout" / d / "reports"
        latest = (rdir / "LATEST").read_text().strip()
        pnr[m] = latest
        gds, deff = rdir / latest / f"{top}.gds", rdir / latest / f"{top}.def"
        spef = scratch / f"{top}.spef"
        item5 = (HERE / "requests" / f"{m}.12mhz.json")
        item5_def = (item5.parent / json.loads(item5.read_text())["def"]).resolve()
        if sha(item5_def) != sha(deff):
            sys.exit(f"{m}: LATEST routed DEF differs from the DEF the item 5 STA request names ({item5_def}); "
                     "the SDF would not describe the geometry item 5 timed")
        run([KLT, "extract", str(gds), "--deck", "sky130", "--top", top, "--pdk", "sky130A", "--pdk-root", PDK_ROOT,
             "--parasitics", "--spef", str(spef), "--def-net-names", "--def-net-connections", str(deff),
             "-o", str(scratch / f"{top}.extract.spice"), "--format", "json"])
        req = json.loads((HERE / "requests" / f"{m}.12mhz.json").read_text())
        if req["pdk"]["corners"] != cs["klt_sta_pdk_corners"]:
            sys.exit(f"{m}: pdk.corners differs from corner-set.json")
        req["def"], req["spef"], req["sdf"] = str(deff), str(spef), True
        sreq = scratch / f"{m}.sdf.json"
        sreq.write_text(json.dumps(req, indent=2) + "\n")
        env = dict(os.environ, PDK="sky130A", PDK_ROOT=PDK_ROOT)
        rep = json.loads(run([KLT, "sta", str(sreq), "--format", "json"], env=env))
        gate = {c["corner"]: c for c in rep["corners"]}
        for c in cs["klt_sta_pdk_corners"]:
            k = gate[c]
            a = k["spef_annotation"]
            if not (a["design_nets_annotated"] == a["design_nets_total"] and a["delay_changed"]):
                sys.exit(f"{m} {c}: SPEF did not annotate every design net / change delays: {a}")
            if k["timing_status"] != "constrained" or k["worst_slack_ns"] < 0 or k["worst_hold_slack_ns"] < 0:
                sys.exit(f"{m} {c}: timing not clean")
            src = sreq.parent / ".klt" / "sta" / f"{top}.{c}.sdf"
            if not src.is_file():
                sys.exit(f"missing {src}")
            data = src.read_bytes()
            if hashlib.sha256(data).hexdigest() != k["sdf"]["content_hash"].split(":")[1]:
                sys.exit(f"{src}: hash differs from the report's sdf.content_hash")
            (out / "sdf" / f"{m}.{c}.sdf").write_bytes(data)
        text = json.dumps(rep, indent=2).replace(str(REPO), "<repo>").replace(str(scratch), "<scratch>")
        (out / f"{m}.sdf-sta.json").write_text(text + "\n")
        (out / "executed-requests" / f"{m}.sdf.json").write_text(
            json.dumps(req, indent=2).replace(str(REPO), "<repo>").replace(str(scratch), "<scratch>") + "\n")
        rows[m] = (rep, sha(spef), spef.stat().st_size)
        inputs += [gds, deff]
    inputs += [HERE / "requests" / f"{m}.12mhz.json" for m in MACROS] + [HERE / "corner-set.json"]
    lines = [f"{sha(p)}  {p.relative_to(REPO)}\n" for p in inputs]
    (out / "inputs.sha256").write_text("".join(lines))
    ver = lambda c: subprocess.run(c, capture_output=True, text=True).stdout.strip().splitlines()[0]
    first = rows["sar-sequencer"][0]
    L = [f"# Post-route SDF generation record: {rid}", "", "## Provenance",
         f"- `klt` version: {ver([KLT, '--version'])}; OpenROAD/OpenSTA {first['engine_version']}",
         f"- PDK: sky130A under PDK_ROOT, reported by klt as `{first['provenance']['pdk']['version']}`"
         f" (compatibility: `{(first['provenance']['pdk'].get('compatibility') or {}).get('status', 'no mismatch reported')}`)",
         f"- repo commit (HEAD when run): `{head}`; input hashes in `runs/{rid}/inputs.sha256`",
         "- P&R inputs (`reports/LATEST` of each macro): " + ", ".join(f"`{m}` -> `{pnr[m]}`" for m in MACROS),
         "- Each LATEST routed DEF is byte-identical to the DEF named by the macro's `requests/<macro>.12mhz.json` (the item 5 STA geometry; asserted by the script), so the SDF describes the geometry item 5 timed. LATEST is used because it is the current P&R record (issue #679's Champion note).",
         "", "## Method", "",
         "1. `klt extract --parasitics --def-net-names --def-net-connections <routed DEF>` on the routed GDS writes a SPEF whose nets carry the DEF's instance-pin connections, so OpenSTA can attach them (without `--def-net-connections` only 44 of 240 SPEF nets resolved and the delays did not change).",
         "2. `klt sta` with that `spef` and `sdf: true`, at the four Liberty corners of `corner-set.json`, 12 MHz constraints identical to `requests/<macro>.12mhz.json`, writes one SDF per corner.",
         "", "## Results", "",
         "| Macro | Corner | Worst setup slack (ns) | Worst hold slack (ns) | Design nets annotated | SDF sha256 |", "|---|---|---:|---:|---:|---|"]
    for m, (rep, sp, _) in rows.items():
        for k in rep["corners"]:
            a = k["spef_annotation"]
            L.append(f"| `{m}` | {k['corner']} | {k['worst_slack_ns']} | {k['worst_hold_slack_ns']} | {a['design_nets_annotated']}/{a['design_nets_total']} | `{k['sdf']['content_hash'][7:23]}…` |")
    L += ["", "SPEF sha256 (scratch artefact, regenerated by this script, not committed): " +
          ", ".join(f"`{m}` `{rows[m][1][:16]}…`" for m in MACROS), "",
          "## Limits", "",
          "- Ideal clock, as in the item 5 STA: the routed clock tree is not propagated, so clock-tree skew is not in the SDF's register timing arcs beyond what OpenSTA's ideal-clock model gives.",
          "- The extracted SPEF is `klt extract`'s lumped-star RC model (one R and one C per net), not a distributed extraction; `spef_annotation.annotation_complete` is `false` in the reports because the SPEF also names nets the DEF-linked design does not have (reader warnings); every design net is annotated (`design_nets_annotated == design_nets_total`) and `delay_changed` is `true`.",
          "- The PDK compatibility field is as printed above; see the functional record for how the Verilog cell models relate to it.",
          "- Routed `sar_sequencer` is the 36-instance issue-#102 netlist (issue #680).", ""]
    rec.write_text("\n".join(L))
    print(rid)


main()

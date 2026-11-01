#!/usr/bin/env python3
"""Mint one append-only SDF-annotated functional-verification record (issue
#679): re-runs the bit-exact bench of each digital macro against its POST-ROUTE
gate-level netlist with the back-annotated SDF of a `sim/digital-sta/runs/<sta-id>/`
run (made by sim/digital-sta/bin/run-sdf.py), once per Liberty corner, plus two
controls per macro that show the annotation is doing something:

    <macro>.<corner>.json          `klt functional-verification` report, options.sdf set  (the evidence)
    <macro>.control-short-settle.json   same SDF, outputs sampled 0.1 ns after the edge   (must FAIL)
    <macro>.control-no-sdf.json         same timing models, no SDF, 0.1 ns settle          (must PASS)

Writes sim/digital-functional/runs/<id>/ (+ inputs.sha256) and
sim/digital-functional/records/<id>-sdf.md. `options.sdf.file` is absolute (a
klt requirement); the committed copies name `<repo>/...` instead, so the
reports are byte-identical on every checkout and cite a path that resolves
nowhere (signoff/check_evidence_hashes.py re-hashes the real inputs from
inputs.sha256).

    PDK=sky130A PDK_ROOT=~/.ciel KLT=.venv-signoff/bin/klt python3 -I \\
        sim/digital-functional/bin/run-sdf-record.py <sta-run-id>

Needs the pinned klt with the functional-verification extra (cocotb) + iverilog.
"""
import datetime, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
KLT = os.environ.get("KLT", "klt")
CORNERS = ("tt_025C_1v80", "tt_100C_1v80", "ss_100C_1v60", "ff_n40C_1v95")
HALF_NS, SETTLE_NS, SHORT_NS = "42", "40", "0.1"  # period 84 ns >= the 12 MHz STA request's 83.33 ns
CONTROL_CORNER = "ss_100C_1v60"
MACROS = {
    "sar-sequencer": ("sar_sequencer", "test_sar_sequencer_sdf", "layout/sar-sequencer/reports"),
    "top-glue": ("top_glue", "test_top_glue_sdf", "layout/top-glue/reports"),
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def klt_fv(req, settle):
    env = dict(os.environ, SAR_TB_HALF_NS=HALF_NS, SAR_TB_SETTLE_NS=settle)
    r = subprocess.run([KLT, "functional-verification", str(req), "--format", "json"],
                       capture_output=True, text=True, cwd=REPO, env=env)
    if not r.stdout.strip():
        sys.exit(f"klt functional-verification {req} produced no output rc={r.returncode}\n{r.stderr}")
    return json.loads(r.stdout)


def scrub(doc):
    return json.dumps(doc, indent=2).replace(str(REPO), "<repo>") + "\n"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: run-sdf-record.py <sim/digital-sta run id holding sdf/>")
    sta_id = sys.argv[1]
    sta = REPO / "sim/digital-sta/runs" / sta_id
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + head
    run, rec = HERE / "runs" / rid, HERE / "records" / f"{rid}-sdf.md"
    if run.exists() or rec.exists():
        sys.exit(f"{rid} already exists; records are append-only")
    (run / "executed-requests").mkdir(parents=True)
    scratch = Path(tempfile.mkdtemp(prefix="klt-fv-sdf-"))
    models = HERE / "models/sky130_fd_sc_hd_subset_timing.v"
    rows, ctl, nets, inputs = {}, {}, {}, [models]
    for m, (top, tb, rdir) in MACROS.items():
        latest = (REPO / rdir / "LATEST").read_text().strip()
        net = REPO / rdir / latest / f"{top}_post_route.v"
        nets[m] = (latest, net)
        inputs.append(net)
        base = {"sources": [str(models), str(net)], "hdl_toplevel": top, "engine": "icarus",
                "testbench": {"module": tb, "search_path": str(HERE / "tb")}}

        def request(name, sdf):
            d = dict(base)
            if sdf:
                d["options"] = {"sdf": {"file": str(sta / "sdf" / f"{m}.{sdf}.sdf"), "corner": "typ"}}
            p = scratch / f"{m}.{name}.json"
            p.write_text(json.dumps(d, indent=2) + "\n")
            (run / "executed-requests" / f"{m}.{name}.json").write_text(scrub(d))
            return p

        for c in CORNERS:
            rows[m, c] = klt_fv(request(c, c), SETTLE_NS)
            (run / f"{m}.{c}.json").write_text(scrub(rows[m, c]))
            inputs.append(sta / "sdf" / f"{m}.{c}.sdf")
        ctl[m, "short"] = klt_fv(request("control-short-settle", CONTROL_CORNER), SHORT_NS)
        ctl[m, "nosdf"] = klt_fv(request("control-no-sdf", None), SHORT_NS)
        (run / f"{m}.control-short-settle.json").write_text(scrub(ctl[m, "short"]))
        (run / f"{m}.control-no-sdf.json").write_text(scrub(ctl[m, "nosdf"]))
    # refuse to mint unless the evidence is what the record will claim
    for (m, c), r in rows.items():
        s = (r.get("environment") or {}).get("sdf") or {}
        if not (r.get("failed_count") == 0 and r.get("test_count") and s.get("annotated") is True):
            sys.exit(f"{m} {c}: not a clean annotated run: {r.get('error') or r.get('failed_count')} {s}")
    for m in MACROS:
        if ctl[m, "short"].get("failed_count", 0) < 1:
            sys.exit(f"{m}: short-settle control did not fail; the annotated delays are not observable at this settle time")
        if ctl[m, "nosdf"].get("failed_count") != 0 or not ctl[m, "nosdf"].get("test_count"):
            sys.exit(f"{m}: no-SDF control did not pass")
    inputs += [HERE / "tb" / f for f in ("sar_ref.py", "test_sar_sequencer_sdf.py", "test_top_glue_sdf.py")]
    inputs += [sta / "inputs.sha256"]
    (run / "inputs.sha256").write_text("".join(f"{sha(p)}  {p.relative_to(REPO)}\n" for p in inputs))
    ver = lambda c: subprocess.run(c, capture_output=True, text=True).stdout.strip().splitlines()[0]
    env = rows["sar-sequencer", CORNERS[0]]["environment"]
    L = [f"# Post-route SDF-annotated functional verification record: {rid}", "", "## Provenance",
         f"- `klt` version: {ver([KLT, '--version'])}; engine {env['engine']} {env['engine_version']}; cocotb {env['cocotb_version']}",
         f"- SDF source run: `sim/digital-sta/runs/{sta_id}/sdf/` (record `sim/digital-sta/records/{sta_id}-sdf.md`; corners are the item 5 Liberty corners)",
         "- Netlists (P&R `reports/LATEST` when run): " + ", ".join(f"`{m}` `{nets[m][1].relative_to(REPO)}`" for m in MACROS),
         f"- repo commit (HEAD when run): `{head}`; every input's hash is in `runs/{rid}/inputs.sha256`",
         f"- Clock: half period {HALF_NS} ns (period {2 * int(HALF_NS)} ns, no tighter than the 12 MHz STA request's 83.33 ns); outputs compared {SETTLE_NS} ns after each edge / input change (before the next clock edge's input change at {HALF_NS} ns). SDF corner selector: `typ`.",
         "", "## Results (post-route gate-level, SDF back-annotated)", "",
         "| Macro | SDF Liberty corner | Tests | Passed | Failed | `environment.sdf.annotated` | `partial` |", "|---|---|---:|---:|---:|---|---|"]
    for (m, c), r in rows.items():
        s = r["environment"]["sdf"]
        L.append(f"| `{m}` | {c} | {r['test_count']} | {r['passed_count']} | {r['failed_count']} | {str(s['annotated']).lower()} | {str(s.get('partial')).lower()} |")
    drops = sorted({(k, v["count"]) for r in rows.values() for k, v in (r["environment"]["sdf"].get("dropped") or {}).items()})
    L += ["", "`environment.sdf.dropped` across the reports: " + (", ".join(f"`{k}` ({n})" for k, n in drops) or "none") + ". "
          "Icarus does not implement SDF `TIMINGCHECK`, so **setup/hold/width limits are not checked by this simulation**; they are covered only by the static timing in `sim/digital-sta/` (ideal clock). "
          "`partial: true` is that drop, nothing else.", "",
          "## Controls", "",
          f"Both at {SHORT_NS} ns settle (outputs sampled {SHORT_NS} ns after an edge), SDF = `{CONTROL_CORNER}`:", "",
          "| Macro | Same SDF (expected: fail) | Same models, no SDF (expected: pass) |", "|---|---|---|"]
    for m in MACROS:
        a, b = ctl[m, "short"], ctl[m, "nosdf"]
        L.append(f"| `{m}` | {a['failed_count']} of {a['test_count']} tests fail | {b['passed_count']} of {b['test_count']} pass |")
    L += ["", "The controls show the annotated delays are visible to the bench (a bench that cannot see delay would pass with the short settle too); they are not a coverage claim.", "",
          "## What this does and does not show", "",
          f"- Each cited report is the same bit-exact bench as the zero-delay record (`tb/test_*_sdf.py` differs only in taking its timing from the environment), run on the routed netlist with the SDF's IOPATH/INTERCONNECT delays applied, at each of the four item 5 Liberty corners: outputs match `tb/sar_ref.py` {SETTLE_NS} ns after every edge at an {2 * int(HALF_NS)} ns period.",
          "- It does **not** show setup/hold margin (TIMINGCHECK dropped, above) or the ADC conversion rate. The SDF comes from an ideal-clock STA with a lumped RC SPEF; see the SDF record's Limits.",
          "- Cell models are the PDK's own timing-bearing Verilog (`models/sky130_fd_sc_hd_subset_timing.v`, `bin/extract-cell-models.py --timing`), whose placeholder delays are zero; all delay therefore comes from the SDF.",
          "- Only the corners `corner-set.json` can time (four stock Liberty corners) were annotated; its declared gaps are unchanged.",
          "- Routed `sar_sequencer` is the 36-instance issue-#102 netlist, not today's 57-instance schematic (issue #680). The zero-delay record's pre-route reports are minted by klt 0.6.0; these by the version above (uncontrolled difference).",
          "- Provisional: `spec/target-spec.md` is DRAFT (issue #1).", ""]
    rec.write_text("\n".join(L))
    print(rid)


main()

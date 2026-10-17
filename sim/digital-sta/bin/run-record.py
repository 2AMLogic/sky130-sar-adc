#!/usr/bin/env python3
"""Mint one append-only multi-corner STA record for the digital partition
(issue #678): `klt sta` on the routed sar_sequencer and top_glue DEFs at the
12 MHz DR-006 clock, plus the over-fast-clock negative control, then check
the outcome the record claims (positive runs pass every corner, the negative
control fails setup at every corner) before writing anything.

    runs/<id>/<macro>.12mhz.json                   cited evidence
    runs/<id>/<macro>.negative-control-6ghz.json   negative control (fails by design)
    records/<id>.md

    KLT=.venv-signoff/bin/klt PDK=sky130A PDK_ROOT=<dir holding sky130A> \
        python3 sim/digital-sta/bin/run-record.py
"""
import datetime, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
KLT = os.environ.get("KLT", "klt")
MACROS = ("sar-sequencer", "top-glue")
CASES = ("12mhz", "negative-control-6ghz")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    cs = json.loads((HERE / "corner-set.json").read_text())
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + head
    run, rec = HERE / "runs" / rid, HERE / "records" / f"{rid}.md"
    if run.exists() or rec.exists():
        sys.exit(f"{rid} already exists; records are append-only")
    # klt records `def_path` as an ABSOLUTE path, and `klt signoff` re-hashes
    # whatever that path names when it grades. Handing it the DEF inside this
    # (soon deleted) worktree would make the committed grading differ between
    # this machine and every other checkout (`input_verified` true here, null
    # there), so `klt signoff --check` would fail in CI. Instead the DEFs are
    # staged byte-for-byte into a scratch tree that mirrors their repo-relative
    # path; the recorded path then resolves nowhere, identically everywhere,
    # and signoff/check_evidence_hashes.py re-roots the repo-relative suffix and
    # re-hashes the real DEF. The staged copy is asserted identical below.
    stage = Path(tempfile.mkdtemp(prefix="klt-sta-"))
    res, executed = {}, {}
    for m in MACROS:
        for c in CASES:
            req = HERE / "requests" / f"{m}.{c}.json"
            doc = json.loads(req.read_text())
            if doc["pdk"]["corners"] != cs["klt_sta_pdk_corners"]:
                sys.exit(f"{req.name}: pdk.corners differs from corner-set.json")
            real = (req.parent / doc["def"]).resolve()
            staged = stage / real.relative_to(REPO)
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real, staged)
            assert sha(real) == sha(staged)
            doc["def"] = str(staged)
            sreq = stage / "requests" / req.name
            sreq.parent.mkdir(exist_ok=True)
            sreq.write_text(json.dumps(doc, indent=2) + "\n")
            executed[req.name] = doc
            r = subprocess.run([KLT, "sta", str(sreq), "--format", "json"], capture_output=True, text=True, cwd=REPO)
            if r.returncode != 0:
                sys.exit(f"klt sta {req.name} failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
            res[m, c] = json.loads(r.stdout)
    for (m, c), d in res.items():
        for k in d["corners"]:
            if c == "12mhz":
                ok = k["timing_status"] == "constrained" and k["worst_slack_ns"] >= 0 and k["worst_hold_slack_ns"] >= 0 \
                    and k["setup_violation_count"] == 0 and k["hold_violation_count"] == 0
            else:
                ok = k["worst_slack_ns"] < 0 and k["setup_violation_count"] > 0
            if not ok:
                sys.exit(f"unexpected outcome {m} {c} {k['corner']}: {k}")
    run.mkdir(parents=True)
    rec.parent.mkdir(exist_ok=True)
    for (m, c), d in res.items():
        (run / f"{m}.{c}.json").write_text(json.dumps(d, indent=2) + "\n")
    (run / "executed-requests").mkdir()
    for name, doc in executed.items():
        (run / "executed-requests" / name).write_text(json.dumps(doc, indent=2) + "\n")
    shutil.rmtree(stage)
    any_ = next(iter(res.values()))
    prov = any_["provenance"]
    L = [f"# Digital-partition multi-corner STA record: {rid}", "", "## Provenance",
         f"- `klt` {prov['klt_version']}; OpenROAD/OpenSTA {any_['engine_version']}",
         f"- PDK: {prov['pdk']['name']} ({prov['pdk']['version']}; source: {prov['pdk']['source']}). NOTE: `sim/pdk.json` pins open_pdks `c6d73a3...`; this run used the revision named here, installed on the host (issue #669, the re-pin, was still open when this ran). Liberty files are from that tree.",
         "- `def_path` in the reports names a scratch copy of the DEF (byte-identical, hash asserted); `runs/%s/executed-requests/` holds the requests as run. Reason: klt records an absolute path and the grader re-hashes it, so a path inside a deleted worktree would make `klt signoff --check` differ between machines." % rid,
         f"- repo commit (HEAD when run): `{head}`; geometry: the routed DEFs below (`geometry_source: {any_['geometry_source']}`), no SPEF",
         "", "## Constraints (assumptions, not spec values)",
         "- clock `CLK`, ideal (no propagated clock tree), period 83.33 ns (12 MHz, the DR-006 provisional figure; the sample-rate row is DRAFT)",
         "- `input_delay_ns` = `output_delay_ns` = 0.25 T on every non-clock input / every output (the SPICE campaign's COMP_OUT arrival is also 0.25 T); no `set_driving_cell`/`set_load`, so inputs are ideal and outputs unloaded",
         "- negative control: T = 0.16667 ns (6 GHz, the SPICE campaign's own too-fast value), delays 0.25 T", "",
         "## Corner set", "",
         "Nine digital-characterization points (`corner-set.json`); only one has a stock Liberty file, as a declared nearest-temperature mapping:", "",
         "| Point | Liberty | Status |", "|---|---|---|"]
    for o in cs["operating_points"]:
        L.append(f"| `{o['id']}` | {('`' + o['liberty'] + '`') if o['liberty'] else '-'} | {o['status']}: {o['note']} |")
    L += ["", "Timed in addition (stock Liberty files that are not among the nine; labelled, never a substitute):", ""]
    L += [f"- `{s['liberty']}`: {s['role']}" for s in cs["supplementary_corners"]]
    L += ["", "## Results at 12 MHz (cited evidence)", "",
          "| Macro | Liberty corner | timing_status | setup slack (ns) | hold slack (ns) | setup / hold violations |", "|---|---|---|---:|---:|---|"]
    for m in MACROS:
        for k in res[m, "12mhz"]["corners"]:
            L.append(f"| `{m}` | `{k['corner']}` | {k['timing_status']} | {k['worst_slack_ns']} | {k['worst_hold_slack_ns']} | {k['setup_violation_count']} / {k['hold_violation_count']} |")
    L += ["", "## Negative control: 6 GHz clock (fails by design, not citable as passing)", "",
          "| Macro | Liberty corner | setup slack (ns) | hold slack (ns) | setup violations |", "|---|---|---:|---:|---:|"]
    for m in MACROS:
        for k in res[m, "negative-control-6ghz"]["corners"]:
            L.append(f"| `{m}` | `{k['corner']}` | {k['worst_slack_ns']} | {k['worst_hold_slack_ns']} | {k['setup_violation_count']} |")
    L += ["", "## What this does and does not show", "",
          "- Static timing of the digital partition's own routed netlists at its boundary under the stated I/O constraints. It says nothing about the ADC conversion rate, which also depends on the analog partition and the DRAFT sample-rate row.",
          "- Ideal clock: the routed clock tree is not propagated (`klt sta` 0.6.0 has no such option), so register-to-register hold slack here omits clock-tree skew.",
          "- `top_glue` is purely combinational; its `CLK` is only the reference for the I/O delays plus the `CLKN` inverter, and its worst setup slack (about 20.8 ns) is close to what the stated I/O budget alone leaves (T/2 - 0.25 T = 20.8 ns); the limiting path was not extracted, so no logic-depth claim is made.",
          "- The routed `sar_sequencer` is the 36-instance issue-#102 netlist (the schematic has 57; issue #680), not the later issue-#263 schematic (see `sim/digital-functional/README.md`).",
          "- 8 of the nine points have no Liberty file and were not timed. Only `tt_27c_1.80v` is covered, by the 25 C stock file. The slow/fast process skews fs/sf have no coverage at all.",
          "- Provisional: `spec/target-spec.md` is DRAFT (issue #1); T1 item 5 requires a ratified spec.", ""]
    rec.write_text("\n".join(L))
    print(rid)


main()

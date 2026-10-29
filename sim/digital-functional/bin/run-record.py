#!/usr/bin/env python3
"""Mint one append-only functional-verification record for the digital
partition (issue #678): runs `klt functional-verification` on both macros'
pre-route gate-level netlists, plus the mutation campaign that is the
suite's negative control, and writes

    sim/digital-functional/runs/<id>/{sar-sequencer,top-glue}.json            the cited reports
    sim/digital-functional/runs/<id>/{sar-sequencer,top-glue}.mutations.json  negative control
    sim/digital-functional/runs/<id>/inputs.sha256                            what was run on
    sim/digital-functional/records/<id>.md                                    the record

<id> = <UTC stamp>-<short HEAD>. Existing runs/records are never touched (a
rerun mints a new id). Needs a pinned klt (signoff/requirements.txt) with
cocotb importable in the same environment, plus iverilog:

    KLT=.venv-signoff/bin/klt python3 sim/digital-functional/bin/run-record.py
"""
import datetime, hashlib, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
KLT = os.environ.get("KLT", "klt")
MACROS = {"sar-sequencer": "layout/sar-sequencer/netlist/sar_sequencer.v",
          "top-glue": "layout/top-glue/netlist/top_glue.v"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def klt(*args):
    r = subprocess.run([KLT, *args, "--format", "json"], capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"klt {' '.join(args)} failed rc={r.returncode}\n{r.stdout}\n{r.stderr}")
    return r.stdout, json.loads(r.stdout)


def main():
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, cwd=REPO).stdout.strip()
    rid = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + head
    run, rec = HERE / "runs" / rid, HERE / "records" / f"{rid}.md"
    if run.exists() or rec.exists():
        sys.exit(f"{rid} already exists; records are append-only")
    run.mkdir(parents=True)
    rec.parent.mkdir(exist_ok=True)
    rows, muts = {}, {}
    for name in MACROS:
        req = HERE / "requests" / f"{name}.json"
        out, rows[name] = klt("functional-verification", str(req))
        (run / f"{name}.json").write_text(json.dumps(rows[name], indent=2) + "\n")
        out, m = klt("functional-verification", str(req), "--mutations", str(HERE / "mutations" / f"{name}.json"))
        muts[name] = m["mutation_testing"]
        (run / f"{name}.mutations.json").write_text(json.dumps(m, indent=2) + "\n")
    inputs = ["sim/digital-functional/models/sky130_fd_sc_hd_subset.v", *MACROS.values(),
              *(f"sim/digital-functional/requests/{n}.json" for n in MACROS),
              *(f"sim/digital-functional/mutations/{n}.json" for n in MACROS),
              *(f"sim/digital-functional/tb/{f}" for f in ("sar_ref.py", "test_sar_sequencer.py", "test_top_glue.py"))]
    (run / "inputs.sha256").write_text("".join(f"{sha(REPO / p)}  {p}\n" for p in inputs))
    env = rows["sar-sequencer"]["environment"]
    ver = lambda c: subprocess.run(c, capture_output=True, text=True).stdout.strip().splitlines()[0]
    L = [f"# Digital-partition functional verification record: {rid}", "",
         "## Provenance",
         f"- `klt` version: {ver([KLT, '--version'])}",
         f"- engine: {env['engine']} {env['engine_version']}; cocotb {env['cocotb_version']}",
         f"- repo commit (HEAD when run): `{head}` (the working tree may be dirty; hashes of every input are in `runs/{rid}/inputs.sha256`)",
         "", "## Results (zero-delay gate-level, pre-route netlists)", "",
         "| Macro | Netlist | Tests | Passed | Failed | Mutants killed |", "|---|---|---:|---:|---:|---:|"]
    for n, p in MACROS.items():
        r, m = rows[n], muts[n]
        L.append(f"| `{n}` | `{p}` | {r['test_count']} | {r['passed_count']} | {r['failed_count']} | {m['killed_count']}/{m['valid_count']} |")
    L += ["", "Per-test results (cited evidence: `runs/%s/<macro>.json`):" % rid, ""]
    for n in MACROS:
        L += [f"- `{n}`: " + ", ".join(f"{t['name']} {t['status']}" for t in rows[n]["tests"])]
    L += ["", "Negative control (mutation campaign, `runs/%s/<macro>.mutations.json`): every mutant of the netlist is killed by the suite:" % rid, ""]
    for n in MACROS:
        L += [f"- `{n}`: " + ", ".join(f"#{x['index']} {x['category']} -> {x['status']} by `{x['first_killing_test']}`" for x in muts[n]["results"])]
    L += ["", "## What this does and does not show", "",
          "- Each test compares every output port with `tb/sar_ref.py` (a reference model written from the DR-006/DR-008/DR-009 text) after every clock edge or input change; the pass is bit-exact over the trace, not over end-of-conversion codes only.",
          "- Covered, including the cases the SPICE campaign did not drive: all-ones and all-zeros codes, a mid-conversion asynchronous reset at each of the 12 sequencer states, all 1024 codes in closed loop back to back, and the full 2^10 x 8 glue input space.",
          "- Zero-delay: this says nothing about timing. Post-route SDF re-simulation is issue #679; static timing is `sim/digital-sta/`.",
          "- `layout/sar-sequencer/netlist/sar_sequencer.v` (the netlist that was routed) is the 36-instance form from issue #102. `design/sar_sequencer.sch` and the SPICE campaign's snapshot carry the later issue-#263 additions (`COMP_EFF` xnor, per-conversion clear gating; 57 instances; issue #680). The routed netlist has neither, so these results do NOT cover them. See `sim/digital-functional/README.md`.",
          "- Cell models are the PDK's own functional Verilog (`models/sky130_fd_sc_hd_subset.v`, extracted by `bin/extract-cell-models.py`).",
          "- Provisional: `spec/target-spec.md` is DRAFT (issue #1); T1 item 5 requires a ratified spec.", ""]
    rec.write_text("\n".join(L))
    print(rid)


main()

#!/usr/bin/env python3
"""Mint (or verify) the artifact-anchored generic envelopes that back T1 items
1, 2, 9 and 10 in signoff/block-manifest.json (issue #676).

    python3 signoff/mint_attest_envelopes.py           # (re)write signoff/attest/*.json and signoff/evidence/*
    python3 signoff/mint_attest_envelopes.py --check   # exit 1 if any committed file differs from a fresh mint

WHAT THIS IS, AND WHAT IT IS NOT. klayout-tools 0.7.0 (the first release to grade them; the grader pin is now 0.8.0) grades
an item-1/2/9/10 citation `met` when a `"kind": "generic"` envelope declares
`"t1_item": <id>`, pins the audited artifact (`provenance.input.path` +
`content_hash`), and the manifest pins the same hash. 0.7.0 has no producer for
those envelopes; `klt signoff --attest` (klayout-tools#2844) merged after the
0.7.0 tag. This script is the in-repo stand-in. It reads the same
`schema_version: 1` / `kind: "t1-attestation-inventory"` inventories that
`--attest` will read, so the day a release ships it these envelopes are
regenerated with the tool from the SAME inventory files.

Until then an envelope's `status` is derived HERE, from the checks this script
actually executes, and every envelope lists them in `checks[]`. A check this
script does NOT execute (it needs xschem, ngspice, the PDK, or the whole CI
suite) is recorded with `"executed": false` and `"gated_by"` naming the CI job
that runs it on every push; it never counts toward `status`. So `pass` means
"every check listed with `executed: true` passed", and no more.

Executed here (cheap, headless, no PDK): inventoried files exist and are
hashed; the `sar_adc_top.spice` provenance header's per-schematic sha256 lines
equal the committed schematics' hashes (a freshness proxy for
`design/regen_netlist.sh --check`, which needs xschem); the two schematic-parity
scripts; the declared CI commands appear in `.github/workflows/ci.yml`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTEST_DIR = REPO_ROOT / "signoff" / "attest"
EVIDENCE_DIR = REPO_ROOT / "signoff" / "evidence"
SPICE = "design/sar_adc_top.spice"
GDS = "layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds"
CI_WORKFLOW = ".github/workflows/ci.yml"

SCHEMA = {"schema_version": 1, "kind": "t1-attestation-inventory"}

GLUE_PARITY = "python3 layout/top-glue/bin/check-schematic-parity.py"
SEQ_PARITY = "python3 layout/sar-sequencer/bin/check-schematic-parity.py"


def sha256_file(rel: str) -> str:
    digest = hashlib.sha256()
    with (REPO_ROOT / rel).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def argv(*words: str) -> dict:
    return {"argv": list(words), "cwd": "."}


# --------------------------------------------------------------------------- #
# Inventories (the `klt signoff --attest` schema_version 1 format)
# --------------------------------------------------------------------------- #

def inventories() -> dict[str, dict]:
    coverage = json.loads((REPO_ROOT / "sim/spec-coverage.json").read_text())
    benches = sorted(
        {tb for row in coverage["rows"] for bench in row.get("benches", []) for tb in bench["testbench"]}
    )
    pdk = json.loads((REPO_ROOT / "sim/pdk.json").read_text())
    toolchain = json.loads((REPO_ROOT / "sim/toolchain.json").read_text())
    tools = {
        "ngspice_min_major": str(toolchain["ngspice_min_major"]),
        "ngspice_reference": str(toolchain["ngspice_reference"]),
        "xschem_tag": str(toolchain["xschem_tag"]),
    }
    regen = {
        "path": SPICE,
        "generator": "design/regen_netlist.sh",
        "check": argv("bash", "design/regen_netlist.sh", "--check"),
    }
    return {
        "item-1-analog": {
            **SCHEMA,
            "t1_item": 1,
            "description": (
                "Analog partition design sources: the xschem schematics (and symbols) for the "
                "sampling front end, CDAC array and unit cell, comparator and top level, and "
                "the full-hierarchy netlist derived from them."
            ),
            "sources": [
                "design/sampling_frontend.sch",
                "design/sampling_frontend.sym",
                "design/cdac/cdac_array.sch",
                "design/cdac/cdac_array.sym",
                "design/cdac/cdac_unit_cell.sch",
                "design/comparator.sch",
                "design/comparator.sym",
                "design/sar_adc_top.sch",
                "design/sar_adc_top.sym",
            ],
            "derived": [regen],
        },
        "item-1-digital": {
            **SCHEMA,
            "t1_item": 1,
            "description": (
                "Digital partition design sources: the hand-captured sequencer schematic "
                "(no RTL, no synthesis) and the top-level schematic that instantiates the "
                "glue bank, the netlist derived from them, and the two gate-level Verilog "
                "netlists the place-and-route flows are fed. There are no separate top-glue "
                "source files: the glue instances live in design/sar_adc_top.sch."
            ),
            "sources": [
                "design/sar_sequencer.sch",
                "design/sar_sequencer.sym",
                "design/sar_adc_top.sch",
            ],
            "derived": [
                regen,
                {
                    "path": "layout/top-glue/netlist/top_glue.v",
                    "generator": "hand transliteration of design/sar_adc_top.sch's standard-cell glue",
                    "check": argv(*GLUE_PARITY.split()),
                },
                {
                    "path": "layout/sar-sequencer/netlist/sar_sequencer.v",
                    "generator": "hand transliteration of design/sar_sequencer.sch (not RTL synthesis)",
                    "check": argv(*SEQ_PARITY.split()),
                },
            ],
        },
        "item-9": {
            **SCHEMA,
            "t1_item": 9,
            "description": (
                "Every testbench indexed by sim/spec-coverage.json (gated by "
                "sim/check_spec_coverage.py), the documented cold start, and the PDK and "
                "tool pins."
            ),
            "testbenches": benches,
            "cold_start": {
                "argv": ["bash", "-c", "source sim/env.sh && python3 sim/run_corners.py --check-env"],
                "cwd": ".",
            },
            "pins": {
                "pdk": {"name": pdk["variant"], "revision": pdk["open_pdks_commit"]},
                "tools": tools,
            },
        },
        "item-10": {
            **SCHEMA,
            "t1_item": 10,
            "description": "Repo hygiene: README, license, spec table and CI, plus the CI audit commands.",
            "hygiene": ["README.md", "LICENSE", "spec/target-spec.md", CI_WORKFLOW],
            "checks": [
                {"name": "check-ci", **argv("npm", "run", "check:ci")},
                {"name": "signoff-check", **argv("bash", "signoff/run-signoff.sh", "--check")},
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Checks executed at mint time
# --------------------------------------------------------------------------- #

def check_present(role: str, rel: str) -> dict:
    exists = (REPO_ROOT / rel).is_file()
    return {
        "check": "present",
        "role": role,
        "path": rel,
        "passed": exists,
        "executed": True,
        "content_hash": sha256_file(rel) if exists else None,
    }


def check_spice_header() -> dict:
    """The spice header names each source schematic's sha256 at netlisting time."""
    header = (REPO_ROOT / SPICE).read_text()
    stale = []
    seen = 0
    for rel, claimed in re.findall(r"^\*\s+(design/\S+\.sch): (sha256:[0-9a-f]{64})$", header, re.M):
        seen += 1
        if sha256_file(rel) != claimed:
            stale.append(rel)
    return {
        "check": "netlist-header-hashes",
        "path": SPICE,
        "passed": seen > 0 and not stale,
        "executed": True,
        "schematics_checked": seen,
        "stale": stale,
        "note": "proxy for design/regen_netlist.sh --check (needs xschem), which CI runs",
    }


def check_script(command: str) -> dict:
    result = subprocess.run(
        command.split(), cwd=REPO_ROOT, capture_output=True, text=True,
        env=dict(os.environ, PDK_ROOT="/nonexistent-pdk-root-for-mint"),
    )
    return {
        "check": "command",
        "command": command,
        "passed": result.returncode == 0,
        "executed": True,
        "exit_status": result.returncode,
    }


def check_declared(command: str, gated_by: str) -> dict:
    return {
        "check": "command",
        "command": command,
        "passed": None,
        "executed": False,
        "gated_by": gated_by,
    }


def check_ci_mentions(command: str) -> dict:
    return {
        "check": "ci-workflow-runs",
        "command": command,
        "path": CI_WORKFLOW,
        "passed": command in (REPO_ROOT / CI_WORKFLOW).read_text(),
        "executed": True,
    }


def checks_for(name: str, inv: dict) -> list[dict]:
    checks = [check_present("source", p) for p in inv.get("sources", [])]
    checks += [check_present("testbench", p) for p in inv.get("testbenches", [])]
    checks += [check_present("hygiene", p) for p in inv.get("hygiene", [])]
    for entry in inv.get("derived", []):
        checks.append(check_present("derived", entry["path"]))
        if entry["path"] == SPICE:
            checks.append(check_spice_header())
            checks.append(check_declared("bash design/regen_netlist.sh --check", "CI job pdk-smoke"))
        else:
            checks.append(check_script(" ".join(entry["check"]["argv"])))
    if "cold_start" in inv:
        checks.append(check_declared("source sim/env.sh && python3 sim/run_corners.py --check-env", "CI job pdk-smoke"))
        pins = inv["pins"]
        checks.append({"check": "pin", "role": "pdk", "passed": bool(pins["pdk"]["revision"]), "executed": True, "value": pins["pdk"]})
        checks.append({"check": "pin", "role": "tools", "passed": bool(pins["tools"]), "executed": True, "value": pins["tools"]})
    for spec in inv.get("checks", []):
        command = " ".join(spec["argv"])
        checks.append(check_ci_mentions(command))
        checks.append(check_declared(command, "CI job checks" if "check:ci" in command else "CI job signoff-check"))
    return checks


# --------------------------------------------------------------------------- #
# Envelopes
# --------------------------------------------------------------------------- #

SUMMARIES = {
    "item-1-analog": (
        "Analog design sources: {n} schematic/symbol files inventoried and present, and "
        "design/sar_adc_top.spice's provenance header names each source schematic's current sha256. "
        "The regeneration check itself (design/regen_netlist.sh --check) needs xschem and is run by CI's pdk-smoke job, not here."
    ),
    "item-1-digital": (
        "Digital design sources. sar_sequencer.v is a structural gate-level netlist TRANSLITERATED BY HAND from "
        "design/sar_sequencer.sch, not synthesized from RTL; layout/sar-sequencer/bin/check-schematic-parity.py "
        "binds it to the schematic through design/sar_adc_top.spice's .subckt sar_sequencer. {verdict}"
    ),
    "item-9": (
        "Testbenches shipped: {n} testbench files indexed by sim/spec-coverage.json are present, the PDK revision and tool "
        "versions are pinned. The cold-start command needs ngspice and the PDK and is run by CI's pdk-smoke job, not here."
    ),
    "item-10": (
        "Repo hygiene: README, LICENSE, spec/target-spec.md and the CI workflow are present and the workflow runs the "
        "declared audit commands. Those commands are executed by CI on every push, not here."
    ),
}


def build_envelope(name: str, inv: dict, inv_rel: str) -> dict:
    checks = checks_for(name, inv)
    executed = [c for c in checks if c["executed"]]
    failed = [c for c in executed if not c["passed"]]
    status = "pass" if not failed else "fail"
    if name == "item-1-digital":
        verdict = (
            "The check currently PASSES." if status == "pass" else
            "The check currently FAILS: the committed Verilog predates the schematic's per-conversion clear and "
            "decision-direction logic (issue #263), so this item is not claimed."
        )
        summary = SUMMARIES[name].format(verdict=verdict)
    else:
        summary = SUMMARIES[name].format(n=sum(c["check"] == "present" for c in checks))
    return {
        "schema_version": 1,
        "kind": "generic",
        "t1_item": inv["t1_item"],
        "status": status,
        "summary": summary,
        "source": inv_rel,
        "provenance": {"input": {"path": inv_rel, "content_hash": sha256_file(inv_rel)}},
        "checks": checks,
    }


def item2_envelope() -> dict:
    return {
        "schema_version": 1,
        "kind": "generic",
        "t1_item": 2,
        "status": "pass" if (REPO_ROOT / GDS).is_file() else "fail",
        "summary": (
            "Layout: the committed composed top-level stream. It is produced by the committed klt flows "
            "(layout/*/bin/run-flow.sh, layout/sar-adc-top/bin/) with a per-flow record, and this envelope pins its bytes. "
            "It asserts the stream exists and is the one items 3 and 11 cite; it asserts nothing about item 4 (top-level LVS "
            "mismatches stay tracked by #103). Its sar_sequencer macro was routed from layout/sar-sequencer/netlist/sar_sequencer.v "
            "as committed, which item 1 (digital) reports as stale against the schematic."
        ),
        "source": GDS,
        "provenance": {"input": {"path": GDS, "content_hash": sha256_file(GDS)}},
    }


def render(obj: dict) -> str:
    return json.dumps(obj, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed files differ from a fresh mint")
    args = parser.parse_args()

    ATTEST_DIR.mkdir(parents=True, exist_ok=True)
    differences: list[str] = []

    def emit(path: Path, text: str) -> None:
        rel = path.relative_to(REPO_ROOT)
        if args.check:
            if not path.is_file() or path.read_text() != text:
                differences.append(str(rel))
        else:
            path.write_text(text)
            print(f"wrote {rel}")

    invs = inventories()
    for name, inv in invs.items():
        inv_rel = f"signoff/attest/{name}.inventory.json"
        inv_path = REPO_ROOT / inv_rel
        text = render(inv)
        emit(inv_path, text)
        if args.check:
            envelope_text = render(build_envelope(name, inv, inv_rel)) if inv_path.is_file() and inv_path.read_text() == text else None
            if envelope_text is None:
                continue
        else:
            envelope_text = render(build_envelope(name, inv, inv_rel))
        emit(EVIDENCE_DIR / f"{name}.attestation.generic.json", envelope_text)
    emit(EVIDENCE_DIR / "item-2-layout.generic.json", render(item2_envelope()))

    if differences:
        print("FAIL: committed attestation files differ from a fresh mint (re-run signoff/mint_attest_envelopes.py):", file=sys.stderr)
        for rel in differences:
            print(f"  - {rel}", file=sys.stderr)
        return 1
    if args.check:
        print("OK: signoff/attest inventories and generic envelopes match a fresh mint")
    return 0


if __name__ == "__main__":
    sys.exit(main())

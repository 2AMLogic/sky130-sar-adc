#!/usr/bin/env python3
"""Ablation cross-check for the analog ground mesh (issue #377).

Answers one question, with a measurement rather than an argument:

    **Is the drawn mesh what joins the three analog blocks' grounds, or is
    the substrate?**

Why the question needs a measurement at all
-------------------------------------------
Every ordinary verdict this flow produces is blind to it. `klt extract`'s
sky130 deck ties every NMOS body to one synthesized global substrate net via
`connect_global`, so the composed layout reports a single `GND|VGND|VSS` net
whether or not a single micron of ground metal is drawn -- and it did exactly
that before issue #377 existed (`reports/20260924-214710-b323061/
extract.json`, 692 devices on one net). `klt drc` grades spacing, not
connectivity. `klt lvs` compares against a reference whose `.GLOBAL GND`
makes the same assumption. A clean pass on all three is therefore NOT evidence
that the mesh is present, let alone correct -- which is the same reading error
DR-012 was written to retire one level up, where a clean `klt erc` supply
verdict on `GND` was taken to mean more than "one island".

`klt erc` is the one tool here that models DRAWN CONDUCTOR ONLY: it walks the
stackup and vias declared in `erc-supply-spec.json` and reports how many
electrical islands each declared supply resolves to. It has no substrate
model at all. So the mesh is exactly what its island count is sensitive to,
and cutting the mesh is a prediction this script can falsify:

    full layout  -> `GND` resolves to ONE island   (clean)
    mesh ablated -> `GND` resolves to MORE than one (erc.unconnected_net)

If the ablated run came back clean too, the mesh would be decorative and this
script would say so.

The third leg needs a second question
-------------------------------------
That island count covers two of the mesh's three members and not the third,
and the difference is a naming one, not a wiring one. `comparator` and
`sampling_frontend` both label their ground terminal `GND`, so cutting the
mesh leaves two islands *of a declared supply* and `klt erc` reports it.
`cdac_array`'s terminal is labelled `VSS` -- that sub-block's own schematic
port name -- and `VSS` is not a declared supply in the graded spec, so its
orphaned island in the ablated run has no declared name for `klt erc` to
complain about. Reading the 2-island finding as covering all three legs
would be a smaller version of exactly the over-read this script exists to
prevent.

So the same two GDS are graded a second time against a DIAGNOSTIC spec --
the graded one plus a `VSS` supply entry, built here in the work directory
and never committed -- which turns the third leg into a finding either way:

    full layout  -> `GND` and `VSS` are ONE island (erc.supply_short)
    mesh ablated -> no such short; `GND` splits instead

A short between two declared supplies is normally a defect. Here it is the
measurement: `klt erc` sees drawn conductor and nothing else, so "these two
labels are the same electrical net" is a statement about metal, which is
precisely the claim the mesh makes about `cdac_array`'s terminal. The graded
spec deliberately does NOT declare `VSS` -- doing so would turn this block's
own T1 item 11 record red over a short that is the design -- which is why
this pass is a separate, scratch-spec diagnostic reported beside the
ablation rather than a change to `erc-supply-spec.json`.

What "ablated" means here
-------------------------
`build_layout.py --ablate-ground-mesh` re-emits the identical assembly with
DR-012's `GND` pad drawn exactly as issue #362 shipped it (riser on
`comparator`'s own `GND` pin, met4 stub south, pad label at the same
coordinate) and issue #377's mesh -- the trunk, the three droppers, the two
sub-block risers -- omitted. Nothing else differs: same placement, same
sub-block GDS (which still draw their own `GND`/`VSS` terminals), same ERC
spec, same `klt` build. See `analog_ground_pad_without_mesh()`.

Usage
-----
Run me with the pinned ERC venv's Python (`layout/bin/setup-erc-venv.sh`),
pointing at a record directory `run-flow.sh` already produced -- this script
re-uses that record's own copies of the five sub-block GDS files, so the
ablated variant is composed from byte-identical inputs:

    layout/.venv-erc/bin/python layout/sar-adc-top/bin/probe-ground-mesh.py \
        layout/sar-adc-top/reports/<record-id> \
        -o layout/sar-adc-top/erc-reports/<erc-record-id>/ground-mesh-ablation.json

Only the summary JSON is written into the record: the ablated GDS and its own
ERC envelope are regenerable from the record's committed inputs by re-running
this script, and go to a scratch work directory (`--work-dir`).

Exit codes: 0 if BOTH predictions held (full clean / ablated split, and the
third-leg short present only in the full variant), 3 if either did not (the
verdict this script exists to be able to report), 1 if it could not run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

TOP_CELL = "gen_compose_0"
ROUTE_CELL_NAME = "SAR_ADC_TOP_ROUTE"
#: Every input `build_layout.py`'s own compose request names, copied out of the
#: graded record so both variants are composed from byte-identical inputs.
#:
#: The first five are `blocks[].cell` entries -- sub-block GDS files
#: `run-flow.sh` pulled in from each sub-block's own committed record. The last
#: two are the decoupling unit cell of issue #440: `klt gen cap_array`'s own
#: response (`decap.json`, which is how the compose request names it -- a
#: `blocks[].generator_report`, because `run-flow.sh` GENERATES this cell during
#: the run) plus the stream that response points at. Both are taken from the
#: record rather than regenerated, which is the whole point: the two ablation
#: variants and the record itself then place the same bytes, so the arms differ
#: by the mesh and nothing else.
BLOCK_GDS = (
    "cdac_array.gds",
    "sampling_frontend.gds",
    "comparator.gds",
    "sar_sequencer.gds",
    "seln_inverters.gds",
    "decap.json",
    "decap_unit.gds",
)
#: The declared supply this ablation is about. The other three (`VDD`,
#: `VPWR`, `VGND`) are reported too, as controls: the ablation must not move
#: them, and a run where it does is measuring something other than the mesh.
SUPPLY = "GND"

#: `cdac_array`'s own ground terminal label -- its schematic port name, NOT a
#: declared supply of the graded spec. See this module's docstring, "The third
#: leg needs a second question", for why the diagnostic pass declares it and
#: the graded spec must not.
THIRD_LEG_LABEL = "VSS"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode not in (0, 3):
        sys.exit(
            f"probe-ground-mesh.py: command failed ({proc.returncode}): "
            f"{' '.join(cmd)}\n{proc.stderr}"
        )
    return proc


def compose(
    klt: str,
    work: pathlib.Path,
    record: pathlib.Path,
    build_layout: pathlib.Path,
    variant: str,
    ablate: bool,
) -> pathlib.Path:
    """Re-run this flow's own draw + gen-compose steps into `work/<variant>`."""
    out = work / variant
    out.mkdir(parents=True, exist_ok=True)
    for name in BLOCK_GDS:
        shutil.copy(record / name, out / name)
    cmd = [sys.executable, str(build_layout), str(out)]
    if ablate:
        cmd.append("--ablate-ground-mesh")
    run(cmd)
    # `klt draw`'s JSON envelope goes to stdout; `gen-compose` reads it back
    # as the routing block's own `generator_report`, so it has to land on
    # disk under that name -- exactly as run-flow.sh's own redirect does.
    drawn = run(
        [
            klt, "draw", "--params", "draw.request.json",
            "--cell-name", ROUTE_CELL_NAME, "-o", "route.gds", "--format", "json",
        ],
        cwd=out,
    )
    (out / "draw.json").write_text(drawn.stdout)
    run([klt, "gen-compose", "compose.request.json", "--format", "json"], cwd=out)
    gds = out / f"{TOP_CELL}.gds"
    if not gds.is_file():
        sys.exit(f"probe-ground-mesh.py: gen-compose wrote no {gds}")
    target = out / f"sar_adc_top.{variant}.gds"
    gds.rename(target)
    return target


def erc(klt: str, gds: pathlib.Path, spec: pathlib.Path, out: pathlib.Path) -> dict:
    proc = run(
        [klt, "erc", str(gds), str(spec), "--pdk", "sky130", "--deck", "sky130",
         "--format", "json"]
    )
    report = json.loads(proc.stdout)
    out.write_text(json.dumps(report, indent=2) + "\n")
    return report


def supply_islands(report: dict) -> dict[str, dict]:
    """Per declared supply: how many islands it resolved to, per `klt erc`.

    `klt erc` reports a supply that resolves to more than one island as an
    `erc.unconnected_net` finding naming it, and says nothing about a supply
    that resolves to exactly one -- so "no finding" IS the one-island case,
    and the island count comes from the finding's own payload when there is
    one. Both readings are recorded verbatim below rather than collapsed to a
    boolean, so a future `klt` that reports islands differently is visible as
    a format change rather than as a silent verdict flip.
    """
    out: dict[str, dict] = {}
    for finding in report.get("erc_findings", []):
        net = finding.get("net")
        if net is None:
            continue
        entry = out.setdefault(net, {"findings": []})
        entry["findings"].append(
            {
                "rule": finding.get("rule"),
                "description": finding.get("description"),
                "islands": finding.get("islands") or finding.get("island_count"),
            }
        )
    return out


def diagnostic_spec(spec: pathlib.Path, work: pathlib.Path) -> pathlib.Path:
    """The graded ERC spec plus a `VSS` supply entry, written to the work dir.

    NEVER written back into `layout/sar-adc-top/`: declaring `VSS` in the
    graded spec would make this block's own T1 item 11 record report an
    `erc.supply_short` for a short that IS the design. See this module's
    docstring, "The third leg needs a second question".
    """
    doc = json.loads(spec.read_text())
    doc["nets"] = list(doc.get("nets", [])) + [
        {
            "name": THIRD_LEG_LABEL,
            "kind": "supply",
            "_comment": [
                "DIAGNOSTIC ONLY -- added by bin/probe-ground-mesh.py in a",
                "scratch copy of layout/sar-adc-top/erc-supply-spec.json, so",
                "that `cdac_array`'s own ground terminal label becomes a",
                "declared name klt erc can report on. The graded spec does",
                "not declare it and must not.",
            ],
        }
    ]
    out = work / "erc-supply-spec.with-vss.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    return out


def shorted_to_supply(report: dict, label: str) -> list[dict]:
    """`erc.supply_short` findings naming BOTH `SUPPLY` and `label`.

    `klt erc` files a short under one of the two nets it names, so match on
    the description text rather than on the finding's own `net` key, and
    record the finding verbatim either way.
    """
    hits = []
    for finding in report.get("erc_findings", []):
        if finding.get("rule") != "erc.supply_short":
            continue
        description = str(finding.get("description", ""))
        if f"'{SUPPLY}'" in description and f"'{label}'" in description:
            hits.append(
                {"rule": finding.get("rule"), "description": description}
            )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=pathlib.Path, help="a reports/<record-id> directory")
    parser.add_argument("-o", "--out", type=pathlib.Path, required=True)
    parser.add_argument("--work-dir", type=pathlib.Path, default=None)
    parser.add_argument("--klt", default=None, help="klt binary (default: layout/.venv-erc/bin/klt)")
    args = parser.parse_args()

    bin_dir = pathlib.Path(__file__).resolve().parent
    block_dir = bin_dir.parent
    layout_dir = block_dir.parent
    repo_root = layout_dir.parent
    klt = args.klt or str(layout_dir / ".venv-erc" / "bin" / "klt")
    spec = block_dir / "erc-supply-spec.json"
    record = args.record.resolve()

    work = args.work_dir or pathlib.Path(tempfile.mkdtemp(prefix="ground-mesh-probe-"))
    work.mkdir(parents=True, exist_ok=True)

    diag_spec = diagnostic_spec(spec, work)

    variants = {}
    third_leg = {}
    for variant, ablate in (("full", False), ("ablated", True)):
        gds = compose(klt, work, record, bin_dir / "build_layout.py", variant, ablate)
        report = erc(klt, gds, spec, work / f"erc.{variant}.json")
        diag = erc(klt, gds, diag_spec, work / f"erc.{variant}.with-vss.json")
        third_leg[variant] = {
            "erc_status": diag.get("erc_status"),
            "erc_finding_count": diag.get("erc_finding_count"),
            "shorted_to_supply": shorted_to_supply(diag, THIRD_LEG_LABEL),
            "per_net": supply_islands(diag),
            "spec_content_hash": diag.get("provenance", {}).get("spec", {}).get("content_hash"),
        }
        variants[variant] = {
            # File NAME only, never this machine's scratch path: this summary
            # is committed evidence, and an absolute path from one worktree
            # resolves nowhere else (run-erc.sh's own header, issue #355).
            "gds": gds.name,
            "erc_status": report.get("erc_status"),
            "erc_finding_count": report.get("erc_finding_count"),
            "per_net": supply_islands(report),
            "input_content_hash": report.get("provenance", {}).get("input", {}).get("content_hash"),
            "spec_content_hash": report.get("provenance", {}).get("spec", {}).get("content_hash"),
        }

    # The control that makes the comparison mean anything: this script's own
    # `full` recomposition must be BYTE-IDENTICAL to the GDS the record was
    # graded on. If it is not, the two variants differ by something besides
    # the mesh and the ablation is measuring that instead.
    record_hash = "sha256:" + _sha256(record / "sar_adc_top.gds")
    variants["full"]["record_content_hash"] = record_hash
    reproduces_record = variants["full"]["input_content_hash"] == record_hash

    full_findings = variants["full"]["per_net"].get(SUPPLY, {}).get("findings", [])
    ablated_findings = variants["ablated"]["per_net"].get(SUPPLY, {}).get("findings", [])
    controls_moved = sorted(
        net
        for net in set(variants["full"]["per_net"]) | set(variants["ablated"]["per_net"])
        if net != SUPPLY
        and variants["full"]["per_net"].get(net) != variants["ablated"]["per_net"].get(net)
    )
    as_predicted = bool(
        reproduces_record and not full_findings and ablated_findings and not controls_moved
    )

    # The third leg: `cdac_array`'s terminal is joined to `GND` by drawn metal
    # in the full variant and by nothing in the ablated one. Both halves are
    # required -- a short present in BOTH variants would mean something other
    # than the mesh joins them, which is the failure this half exists to catch.
    third_leg_shorted_full = bool(third_leg["full"]["shorted_to_supply"])
    third_leg_shorted_ablated = bool(third_leg["ablated"]["shorted_to_supply"])
    third_leg_as_predicted = third_leg_shorted_full and not third_leg_shorted_ablated

    summary = {
        "schema": "sky130-sar-adc.ground-mesh-ablation/1",
        "issue": 377,
        "record": str(record.relative_to(repo_root)) if record.is_relative_to(repo_root) else str(record),
        "spec": str(spec.relative_to(repo_root)),
        "klt": subprocess.run([klt, "--version"], capture_output=True, text=True).stdout.strip(),
        "supply_under_test": SUPPLY,
        "variants": variants,
        "third_leg_cross_check": {
            "label": THIRD_LEG_LABEL,
            "why": (
                f"`{THIRD_LEG_LABEL}` is `cdac_array`'s own ground terminal "
                "label and is NOT a declared supply of the graded spec, so "
                "the ablation's island count above cannot see that leg. This "
                "pass re-grades the same two GDS against a scratch spec (the "
                f"graded one plus a `{THIRD_LEG_LABEL}` supply entry, written "
                "to the work dir, never committed): a short between the two "
                "declared names IS the claim that drawn metal joins them, "
                "because klt erc models drawn conductor only."
            ),
            "spec": "erc-supply-spec.with-vss.json (scratch, in the work dir)",
            "variants": third_leg,
        },
        "verdict": {
            "as_predicted": as_predicted and third_leg_as_predicted,
            "ablation_as_predicted": as_predicted,
            "full_reproduces_record_gds": reproduces_record,
            "full_is_one_island": not full_findings,
            "ablated_splits": bool(ablated_findings),
            "controls_unmoved": not controls_moved,
            "controls_moved": controls_moved,
            "third_leg_as_predicted": third_leg_as_predicted,
            "third_leg_shorted_to_supply_full": third_leg_shorted_full,
            "third_leg_shorted_to_supply_ablated": third_leg_shorted_ablated,
            "reading": (
                "The mesh, not the substrate, is what joins the three analog "
                "blocks' drawn grounds: removing it (and nothing else) splits "
                f"{SUPPLY} into more than one island, and stops "
                f"`{THIRD_LEG_LABEL}` from being the same electrical net as "
                f"{SUPPLY}, under a connectivity model that sees drawn "
                "conductor only."
                if (as_predicted and third_leg_as_predicted)
                else (
                    "NOT as predicted -- read the per-variant findings before "
                    "quoting this flow's clean ERC verdict as evidence about "
                    "the mesh."
                )
            ),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["verdict"], indent=2))
    print(f"probe-ground-mesh.py: wrote {args.out} (work dir {work})")
    return 0 if (as_predicted and third_leg_as_predicted) else 3


if __name__ == "__main__":
    raise SystemExit(main())

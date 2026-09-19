#!/usr/bin/env python
"""Measure `klt extract --abstract-cells` behaviour on this assembly's own
composed GDS -- the ablation matrix behind README.md's "A fourth shape
measured" section and its 2026-09-19 correction.

Run me with a Python that has the `klayout` module on its path, i.e. this
repo's own pinned venv (`layout/bin/setup-venv.sh`):

    layout/.venv/bin/python layout/sar-adc-top/bin/probe-abstract-cells.py \
        layout/sar-adc-top/reports/<record-id>

Why this exists
---------------
The `--abstract-cells` shape (black-boxing already-independently-verified
sub-blocks so the top-level compare is pure interconnect) was measured once,
by hand, in record 20260915-234004-76f48b9, and reached 6 mismatches instead
of the whole-request compare's 98. It was not adopted because abstracting the
capacitor-array macro also collapsed several of that macro's own separately
labelled pins -- and the top-level nets they connect to -- onto one composite
net name, which no in-repo check could prove benign.

That measurement's recorded *diagnosis* (the macro's label-less, global-net-
only body port being silently dropped from the black box's pin list) turned
out to be wrong, and the upstream fix this repo then waited on for three days
(klayout-tools#1911/#1934) does not resolve the collapse. This script is the
evidence: it re-runs the same extraction under a caller-chosen `klt` build
across five ablations, so the claim "the collapse does/does not track X" is a
committed, re-runnable measurement rather than a one-off note.

Ablations (each written as its own `<prefix>.<variant>.extract.json`):

  three           the README's own shape: cdac_array + sar_sequencer +
                  seln_inverters abstracted, `--pin-source-cells` on.
  cdac-only       only the capacitor-array macro abstracted.
  cdac-no-pinsrc  same, with `--pin-source-cells` omitted -- isolates the
                  collapse from the declared-pin mechanism (#1513/#1515).
  cdac-tied       same as cdac-only, against a variant GDS with a drawn
                  p-substrate tie (tap/psdm/licon/li1/mcon/met1 + a `vsubs`
                  met1 label) added inside the macro, in free area found
                  automatically. Tests whether the dropped label-less body
                  port is what drives the collapse: it resolves the pin count
                  (23 -> 24) without touching the collapse.
  cdac-no-well    same as cdac-only, against a variant GDS with the macro's
                  own nwell + tap geometry stripped. Tests the body-identity
                  reclassification path klayout-tools#1934 fixed.
  seq-seln        sar_sequencer + seln_inverters abstracted, capacitor array
                  left flat -- the known-clean control.

Only the summary JSON (`abstract-probe.<klt-version>.summary.json`) lands in
the record directory: it already carries every verdict this measurement makes
(per-variant net counts, per-macro resolved pin counts, the watched-pin merge,
and each run's own `--abstract-cells` warnings). The bulky per-variant
extraction envelopes, netlists and the two derived GDS variants go to a
scratch work directory (`--work-dir`, a fresh temp dir by default), since all
of them are regenerable from the record's own committed `sar_adc_top.gds` by
re-running this script.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import klayout.db as db

TOP_CELL = "gen_compose_0"
ROUTE_CELL = "route__SAR_ADC_TOP_ROUTE"
CDAC = "cdac_array__cdac_array"
SEQ = "sar_sequencer__sar_sequencer"
SELN = "seln_inverters__seln_inverters"

# The macro pins whose collapse is the thing under measurement. Reported
# explicitly so a summary row is a verdict, not a haystack.
WATCHED_PINS = ("TOP_N", "TOP_P", "VREFN", "VREFP")


def add_substrate_tie(src: pathlib.Path, dst: pathlib.Path, cell_name: str) -> dict:
    """Write `src` to `dst` with a drawn p-substrate tie added inside `cell_name`.

    Placed in the first free 8 um window found inside the cell's own bbox, so
    it shorts nothing: tap + p+ implant + licon1 + li1 + mcon + met1, with a
    `vsubs` text on met1's label layer for the extractor to name it by.
    """
    layout = db.Layout()
    layout.read(str(src))
    cell = layout.cell(cell_name)
    dbu = layout.dbu

    occupied = db.Region()
    for layer_index in layout.layer_indexes():
        occupied += db.Region(cell.begin_shapes_rec(layer_index))
    occupied.merge()

    bbox = cell.bbox()
    window = int(8.0 / dbu)
    free = None
    y = bbox.bottom + 1000
    while y + window < bbox.top and free is None:
        x = bbox.left + 1000
        while x + window < bbox.right:
            candidate = db.Box(x, y, x + window, y + window)
            if (occupied & db.Region(candidate)).is_empty():
                free = candidate
                break
            x += window
        y += window
    if free is None:
        raise SystemExit(f"probe-abstract-cells.py: no free window inside {cell_name}")

    cx, cy = free.center().x, free.center().y

    def box(width_um: float, height_um: float) -> db.Box:
        half_w, half_h = int(width_um / 2 / dbu), int(height_um / 2 / dbu)
        return db.Box(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

    for (layer, datatype, width, height) in (
        (65, 44, 1.0, 1.0),      # tap
        (94, 20, 1.4, 1.4),      # psdm (p+ implant)
        (66, 44, 0.17, 0.17),    # licon1
        (67, 20, 0.8, 0.8),      # li1
        (67, 44, 0.17, 0.17),    # mcon
        (68, 20, 0.8, 0.8),      # met1
    ):
        cell.shapes(layout.layer(layer, datatype)).insert(box(width, height))
    cell.shapes(layout.layer(68, 5)).insert(db.Text("vsubs", db.Trans(cx, cy)))

    layout.write(str(dst))
    return {"at_um": [cx * dbu, cy * dbu], "cell": cell_name}


def strip_well(src: pathlib.Path, dst: pathlib.Path, cell_name: str) -> dict:
    """Write `src` to `dst` with `cell_name`'s own nwell + tap shapes removed."""
    layout = db.Layout()
    layout.read(str(src))
    cell = layout.cell(cell_name)
    cleared = {}
    for layer, datatype in ((64, 20), (65, 44)):
        layer_index = layout.find_layer(layer, datatype)
        if layer_index is None:
            continue
        cleared[f"{layer}/{datatype}"] = cell.shapes(layer_index).size()
        cell.shapes(layer_index).clear()
    layout.write(str(dst))
    return {"cleared": cleared, "cell": cell_name}


def run_extract(klt: str, gds: pathlib.Path, out_dir: pathlib.Path, name: str,
                abstract: list[str], pin_source: bool) -> dict:
    """Run one `klt extract` ablation, returning its own summary row."""
    spice = out_dir / f"{name}.extract.spice"
    envelope = out_dir / f"{name}.extract.json"
    argv = [klt, "extract", str(gds), "--deck", "sky130", "--top", TOP_CELL,
            "-o", str(spice), "--format", "json"]
    if pin_source:
        argv += ["--pin-source-cells", ROUTE_CELL]
    for cell in abstract:
        argv += ["--abstract-cells", cell]
    completed = subprocess.run(argv, capture_output=True, text=True)
    envelope.write_text(completed.stdout)
    if completed.returncode != 0 and not completed.stdout.strip():
        raise SystemExit(f"probe-abstract-cells.py: {name}: klt extract failed\n{completed.stderr}")

    report = json.loads(completed.stdout)
    watched = [m for m in report.get("merged_net_labels", [])
               if any(pin in m["net"].split("|") for pin in WATCHED_PINS)]
    return {
        "variant": name,
        "gds": gds.name,
        "abstract_cells": abstract,
        "pin_source_cells": ROUTE_CELL if pin_source else None,
        "status": report.get("status"),
        "net_count": report.get("net_count"),
        "device_count": report.get("device_count"),
        "top_pin_count": report.get("pin_count"),
        "abstracted_cells": [
            {"cell": c["cell"], "pin_count": c["pin_count"],
             "resolution_source": c.get("resolution_source")}
            for c in report.get("abstracted_cells", [])
        ],
        "watched_pin_merges": watched,
        "abstract_warnings": [w for w in report.get("warnings", []) if "abstract" in w.lower()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("record_dir", type=pathlib.Path,
                        help="a layout/sar-adc-top/reports/<record-id> directory "
                             "holding this flow's own sar_adc_top.gds")
    parser.add_argument("--klt", default=os.environ.get("SAR_ADC_TOP_PROBE_KLT"),
                        help="klt executable to measure (default: the pinned "
                             "layout/.venv/bin/klt, or $SAR_ADC_TOP_PROBE_KLT)")
    parser.add_argument("--tag", default=None,
                        help="output prefix discriminator (default: the measured "
                             "build's own `klt --version` string)")
    parser.add_argument("--work-dir", type=pathlib.Path, default=None,
                        help="scratch directory for the per-variant netlists, "
                             "extraction envelopes and derived GDS variants "
                             "(default: a fresh temp dir) -- only the summary "
                             "JSON is written into the record directory")
    args = parser.parse_args()

    record_dir = args.record_dir.resolve()
    gds = record_dir / "sar_adc_top.gds"
    if not gds.is_file():
        raise SystemExit(f"probe-abstract-cells.py: no sar_adc_top.gds in {record_dir}")

    klt = args.klt or str(record_dir.parents[2] / ".venv" / "bin" / "klt")
    version = subprocess.run([klt, "--version"], capture_output=True, text=True).stdout.strip()
    tag = args.tag or version.replace("klt ", "klt-").replace(" ", "-")
    prefix = f"abstract-probe.{tag}"

    # Bulky, fully regenerable artifacts stay out of the append-only record.
    work_dir = args.work_dir or pathlib.Path(tempfile.mkdtemp(prefix="abstract-probe-"))
    work_dir.mkdir(parents=True, exist_ok=True)

    tied_gds = work_dir / "variant-substrate-tie.gds"
    no_well_gds = work_dir / "variant-no-well-tap.gds"
    tie_info = add_substrate_tie(gds, tied_gds, CDAC)
    strip_info = strip_well(gds, no_well_gds, CDAC)

    rows = [
        run_extract(klt, gds, work_dir, f"{prefix}.three", [CDAC, SEQ, SELN], True),
        run_extract(klt, gds, work_dir, f"{prefix}.cdac-only", [CDAC], True),
        run_extract(klt, gds, work_dir, f"{prefix}.cdac-no-pinsrc", [CDAC], False),
        run_extract(klt, tied_gds, work_dir, f"{prefix}.cdac-tied", [CDAC], True),
        run_extract(klt, no_well_gds, work_dir, f"{prefix}.cdac-no-well", [CDAC], True),
        run_extract(klt, gds, work_dir, f"{prefix}.seq-seln", [SEQ, SELN], True),
    ]

    summary = {
        "schema": "sar-adc-top.abstract-cells-probe/1",
        "klt_version": version,
        "record": record_dir.name,
        "substrate_tie_variant": tie_info,
        "no_well_tap_variant": strip_info,
        "variants": rows,
    }
    summary_path = record_dir / f"{prefix}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"probe-abstract-cells.py: {version} -> {summary_path.name}")
    for row in rows:
        merged = "; ".join(m["net"] for m in row["watched_pin_merges"]) or "none"
        pins = ", ".join(f"{c['cell']}={c['pin_count']}" for c in row["abstracted_cells"])
        print(f"  {row['variant'].split('.')[-1]:16s} nets={row['net_count']:4d} "
              f"abstracted_pins[{pins}]  watched-pin merge: {merged}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

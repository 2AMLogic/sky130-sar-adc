"""Shared `klt gen` invoke/JSON-check/argparse boilerplate for the layout
sub-blocks' `gen_blocks.py` scripts.

Used by `layout/sampling-frontend/bin/gen_blocks.py`,
`layout/comparator/bin/gen_blocks.py`, and
`layout/sampling-frontend-wells/bin/gen_blocks.py`, which import this module
via a `sys.path` insert (see any of those scripts' own header) rather than a
package install, matching this directory's existing `_geometry_common.py` /
`_pfet_devices.py` / `_record_common_strict.py` shared-module convention.

Before this module existed, all three scripts hand-rolled the identical "build
the 13-element `klt gen ... --format json` argv, run it, write the JSON
report, parse it, check `report.get(\"error\")`" block, plus identical
`out_dir`/`--klt`/`--pdk` argparse setup in each script's own `main()` --
`layout/sampling-frontend/bin/gen_blocks.py` had already split it into two
module-level helpers (`_run()`/`_write_and_check()`), the other two scripts
just inlined the same logic directly in their loop bodies instead of picking
that split up. Found and removed as issue #255, the same class of finding as
#163 (duplicated `build_layout.py` helpers) and #161 (duplicated
`render-record.py` helper).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_gen(
    klt: str, pdk: str, generator: str, params: dict, cell_name: str, gds_path: Path
) -> tuple[str, str]:
    """Run `klt gen <generator> --params <json> --pdk <pdk> --cell-name
    <cell_name> -o <gds_path> --format json` and return `(stdout, stderr)`.
    """
    cmd = [
        klt,
        "gen",
        generator,
        "--params",
        json.dumps(params),
        "--pdk",
        pdk,
        "--cell-name",
        cell_name,
        "-o",
        str(gds_path),
        "--format",
        "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.stdout, result.stderr


def write_and_check(block_id: str, stdout: str, stderr: str, json_path: Path) -> dict | None:
    """Write `stdout` (the `klt gen ... --format json` report) to `json_path`,
    parse it, and return the parsed report -- or `None`, after printing a
    `gen_blocks.py:`-prefixed diagnostic to stderr, if `stdout` was not valid
    JSON or the report carries an `error` key.
    """
    json_path.write_text(stdout)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"gen_blocks.py: {block_id}: non-JSON output:\n{stdout}\n{stderr}", file=sys.stderr)
        return None
    if report.get("error"):
        print(f"gen_blocks.py: {block_id}: generator error: {report['error']}", file=sys.stderr)
        return None
    return report


def add_klt_pdk_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add the `out_dir` positional and `--klt`/`--pdk` options every
    `gen_blocks.py` script's `argparse.ArgumentParser` defines identically.
    Returns `parser` for chaining.
    """
    parser.add_argument("out_dir", type=Path, help="directory to write <id>.gds/<id>.json into")
    parser.add_argument("--klt", default="klt", help="path to the klt executable")
    parser.add_argument("--pdk", default="sky130A", help="PDK variant")
    return parser

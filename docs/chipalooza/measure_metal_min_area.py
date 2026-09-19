#!/usr/bin/env python3
"""Measure sky130A's met1-met5 MINIMUM-AREA rules against this repo's own GDS.

Why this script exists (issue #326)
-----------------------------------
`klt drc --deck sky130` is this repo's layout sign-off gate, and every
`layout/**/reports/` record it has minted reports `status: "clean"`. That
verdict is real but *narrow*: at the pinned `klayout-tools==0.5.0`
(`layout/requirements.txt`) the curated sky130 deck authors 47 rules across
five kinds (`width`, `space`, `enclosing`, `separation`, `isolated`) and **no
`area`-kind rule at all**, so sky130A's own minimum-area rules --

    m1.6    min. m1 area  0.083  um^2
    m2.6    min. m2 area  0.0676 um^2
    m3.6    min. m3 area  0.240  um^2
    m4.4a   min. m4 area  0.240  um^2
    m5.4    min. m5 area  4.0    um^2

-- have never looked at any layout in this repository. A shape below one of
those thresholds is a real foundry-rule violation that `klt drc` structurally
cannot see today; the gap is fixed upstream (2AMLogic/klayout-tools#1989,
commit `50cc29c3`) but not yet released, and this repo does not relax a gate to
match the tool it happens to have. This script is the stand-in measurement:
it applies the *same* KLayout primitive the PDK's own deck rule text calls
(`Region#with_area`), against the *same* thresholds and layer numbers, read out
of the pinned PDK install rather than transcribed here -- so it cannot drift
from the PDK, and it retires cleanly once the released deck carries the rules.

Clean room: every number this script uses comes from this repo's own pinned
sky130A install (`sim/pdk.json`: open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b)
and from this repo's own committed GDS records. Nothing is transcribed from
any third-party layout.

WHAT IT MEASURES
----------------
For each of the five metal layers, on each target GDS:

  1. Read the layer number and the minimum-area threshold out of the pinned
     PDK's own `libs.tech/klayout/drc/sky130A_mr.drc` (the `mN_wildcard =
     "L/D"` assignments and the `mN.with_area(0..T).output("<rule>", ...)`
     calls). Nothing about the rule set is hardcoded below.
  2. Flatten the GDS's top cell onto that layer, MERGE it (the DRC deck's
     `polygons(...)` input is merged-semantics, so two abutting drawn
     rectangles are one polygon to the rule -- measuring unmerged shapes
     would report violations the foundry rule does not see), and select the
     polygons whose area is below the threshold with `Region#with_area`.
  3. Report every selected polygon's bounding box and area.

A non-empty selection is a real m1.6/m2.6/m3.6/m4.4a/m5.4 violation.

USAGE
-----
    python3 docs/chipalooza/measure_metal_min_area.py [GDS ...] [options]

With no GDS arguments it measures the *current* record of the top-level
composition plus each of its five sub-block flows (each flow's own
`reports/LATEST` pointer, so it always grades the record the repo is
currently standing behind).

    --json          machine-readable output (per-target, per-layer, per-shape)
    --baseline F    grade the measurement against a baseline of per-target,
                    per-rule allowances (see BASELINE MODE below); without it
                    ANY shape below threshold is a failure
    --pdk-root DIR  PDK search root (default: $PDK_ROOT, else ~/.volare)
    --variant NAME  PDK variant (default: $PDK, else sky130A)
    --repo-root DIR repo root used to resolve the default targets

Exit status:

    0 - every measured layer is clear of its own minimum-area threshold
        (or, in baseline mode, clear of its recorded allowance)
    1 - at least one shape is below threshold / over allowance (each listed)
    2 - usage/environment error (no PDK deck, no klayout module, bad path,
        malformed or stale-keyed baseline file)

BASELINE MODE (issue #338)
--------------------------
This measurement is the CI gate for the invariant issue #326 established --
this repo's own generators draw no isolated sub-minimum-area metal -- and runs
in `.github/workflows/ci.yml`'s PDK-gated `pdk-smoke` job.

A bare run cannot be that gate today, because the composed top level and the
two place-and-routed digital macros carry shapes `klt`'s own place-and-route
emitted, not shapes this repo drew: a known, filed, not-ours finding (#333
here, 2AMLogic/klayout-tools#2072 upstream). `--baseline` separates the two:

  * each allowance is a CEILING on one (target, rule) pair -- MORE shapes
    than the recorded count fails, so a new isolated pad from any of this
    repo's own generators (including the `sar-adc-top` and
    `sampling-frontend` ones #326 actually had to fix) turns CI red;
  * FEWER shapes than the ceiling passes, loudly flagged as a stale
    allowance, so the day #333's shapes stop being emitted the gate does not
    red-line -- it tells you to delete the entry;
  * a (target, rule) with no allowance is gated at zero, so the three flows
    whose geometry this repo hand-authors end to end (`cdac-array`,
    `comparator`, `sampling-frontend`) fail on the first shape;
  * every allowance MUST name the issue that tracks it, and an allowance
    naming a target or rule that was not measured is an error, not a
    silently-ignored line -- a waiver cannot rot unnoticed.

The repo's own baseline is `docs/chipalooza/metal_min_area_baseline.json`,
which today waives exactly #333's shapes and nothing else. When #333 closes,
delete that file and drop `--baseline` from the CI step: one removal, two
lines, no code change.

`--baseline` grades the DEFAULT target set (it is keyed by the flow labels in
`DEFAULT_TARGETS`); pass it without explicit GDS arguments.

Requires the `klayout` Python module -- available in this repo's own
`layout/.venv` (`layout/bin/setup-venv.sh`), which is why this script is NOT
part of the always-on headless `checks` CI job: like `klt` itself it is
PDK- and KLayout-gated. Run it from that venv:

    layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py \\
        --baseline docs/chipalooza/metal_min_area_baseline.json

(The baseline *bookkeeping* -- schema validation, ceiling/stale/unknown-key
arithmetic -- is pure Python and is unit-tested headlessly in
`sim/tests/test_metal_min_area_baseline.py`, which `npm run test` runs on
every push. Only the KLayout measurement itself is PDK-gated.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

#: Default measurement targets: `(label, flow directory, GDS basename)`.
#: The GDS basename is each flow's own top-level artefact -- the same file
#: `layout/sar-adc-top/bin/run-flow.sh` copies in as a composition input for
#: the five sub-blocks, and the composed cell that flow itself writes. Each
#: path is resolved through the flow's own `reports/LATEST` pointer, never a
#: hardcoded record id, so this measures whatever record the repo currently
#: stands behind.
DEFAULT_TARGETS: list[tuple[str, str, str]] = [
    ("sar-adc-top (composed)", "layout/sar-adc-top", "sar_adc_top.gds"),
    ("cdac-array", "layout/cdac-array", "cdac_array.gds"),
    ("comparator", "layout/comparator", "comparator.gds"),
    ("sampling-frontend", "layout/sampling-frontend", "sampling_frontend.gds"),
    ("sar-sequencer", "layout/sar-sequencer", "sar_sequencer.gds"),
    ("seln-inverters", "layout/seln-inverters", "seln_inverters.gds"),
]

#: The metal layer symbols the PDK deck names, in process order. Each one has
#: exactly one `mN.with_area(0..T).output("<rule>", ...)` minimum-area rule and
#: one `mN_wildcard = "L/D"` layer assignment in `sky130A_mr.drc`.
METAL_SYMBOLS = ["m1", "m2", "m3", "m4", "m5"]

#: Schema tag every baseline file must carry, so a future incompatible format
#: is a loud error rather than a silently-misread set of allowances.
BASELINE_SCHEMA = "metal-min-area-baseline/1"

#: Fields each allowance entry must carry. `tracking_issue` and `reason` are
#: mandatory ON PURPOSE (issue #338): an allowance that cannot say which open
#: finding it exists for, and why, is exactly the kind of carve-out that
#: outlives the defect it was written for.
BASELINE_REQUIRED_FIELDS = ("target", "rule", "max_below_min_area", "tracking_issue", "reason")


class MeasurementError(RuntimeError):
    """Usage/environment problem (exit 2), as opposed to a real violation."""


# --------------------------------------------------------------------------- #
# PDK deck parsing -- the rule table is READ, never transcribed.
# --------------------------------------------------------------------------- #
def find_deck(pdk_root: Path, variant: str) -> Path:
    """Locate `<pdk_root>/<variant>/libs.tech/klayout/drc/<variant>_mr.drc`."""
    deck = pdk_root / variant / "libs.tech" / "klayout" / "drc" / f"{variant}_mr.drc"
    if not deck.is_file():
        raise MeasurementError(
            f"no {variant} DRC deck at {deck} -- see sim/pdk.json for the pin "
            f"(install: volare enable --pdk sky130 <open_pdks_commit>)"
        )
    return deck


def parse_min_area_rules(deck_text: str) -> list[dict]:
    """Extract `[{symbol, rule, layer, datatype, min_area_um2}, ...]`.

    Both halves come out of the deck's own text: the layer number from the
    `mN_wildcard = "L/D"` assignment, the threshold and the rule name from the
    `mN.with_area(0..T).output("<rule>", ...)` call that implements it.
    """
    wildcards: dict[str, tuple[int, int]] = {}
    for sym in METAL_SYMBOLS:
        m = re.search(rf'^\s*{sym}_wildcard\s*=\s*"(\d+)/(\d+)"', deck_text, re.MULTILINE)
        if m:
            wildcards[sym] = (int(m.group(1)), int(m.group(2)))

    rules: list[dict] = []
    for sym in METAL_SYMBOLS:
        m = re.search(
            rf"^\s*{sym}\.with_area\(0\.\.([0-9.]+)\)\.output\(\s*\"([^\"]+)\"",
            deck_text,
            re.MULTILINE,
        )
        if not m:
            continue
        if sym not in wildcards:
            raise MeasurementError(
                f"deck declares a minimum-area rule for {sym} but no {sym}_wildcard layer"
            )
        layer, datatype = wildcards[sym]
        rules.append(
            {
                "symbol": sym,
                "rule": m.group(2),
                "layer": layer,
                "datatype": datatype,
                "min_area_um2": float(m.group(1)),
            }
        )
    if not rules:
        raise MeasurementError("no mN.with_area(...) minimum-area rules found in the deck")
    return rules


# --------------------------------------------------------------------------- #
# Measurement
# --------------------------------------------------------------------------- #
def measure_gds(gds_path: Path, rules: list[dict]) -> dict:
    """Apply every rule in `rules` to `gds_path`'s top cell."""
    try:
        import klayout.db as kdb
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MeasurementError(
            "the `klayout` python module is not importable -- run this from "
            "this repo's own layout venv (layout/bin/setup-venv.sh):\n"
            "  layout/.venv/bin/python docs/chipalooza/measure_metal_min_area.py"
        ) from exc

    layout = kdb.Layout()
    layout.read(str(gds_path))
    dbu = layout.dbu
    tops = layout.top_cells()
    if len(tops) != 1:
        names = ", ".join(c.name for c in tops)
        raise MeasurementError(f"{gds_path}: expected exactly one top cell, found: {names}")
    top = tops[0]

    layers = []
    for rule in rules:
        li = layout.find_layer(rule["layer"], rule["datatype"])
        region = kdb.Region()
        if li is not None:
            region.insert(top.begin_shapes_rec(li))
        region.merge()
        # `Region#with_area` is the exact primitive the deck's own rule text
        # calls. Region coordinates are integer DBU, so the um^2 threshold is
        # converted to DBU^2 here (dbu is 0.001 um for every GDS in this repo,
        # making every threshold an exact integer, but the rounding keeps this
        # correct on any dbu).
        max_area_dbu2 = round(rule["min_area_um2"] / (dbu * dbu))
        below = region.with_area(0, max_area_dbu2, False)

        shapes = []
        for poly in below.each():
            box = poly.bbox()
            shapes.append(
                {
                    "area_um2": poly.area() * dbu * dbu,
                    "bbox_um": [
                        box.left * dbu,
                        box.bottom * dbu,
                        box.right * dbu,
                        box.top * dbu,
                    ],
                    "width_um": box.width() * dbu,
                    "height_um": box.height() * dbu,
                }
            )
        shapes.sort(key=lambda s: (s["area_um2"], s["bbox_um"]))
        layers.append(
            {
                "rule": rule["rule"],
                "symbol": rule["symbol"],
                "layer": rule["layer"],
                "datatype": rule["datatype"],
                "min_area_um2": rule["min_area_um2"],
                "merged_polygons": region.count(),
                "below_min_area": len(shapes),
                "shapes": shapes,
            }
        )

    return {
        "gds": str(gds_path),
        "top_cell": top.name,
        "dbu_um": dbu,
        "layers": layers,
        "total_below_min_area": sum(layer["below_min_area"] for layer in layers),
    }


# --------------------------------------------------------------------------- #
# Target resolution
# --------------------------------------------------------------------------- #
def resolve_default_targets(repo_root: Path) -> list[tuple[str, str, Path]]:
    """Resolve each `DEFAULT_TARGETS` entry through its flow's `reports/LATEST`.

    Returns `(target_key, display_label, gds_path)`. `target_key` is the
    record-independent flow label -- it is what a baseline file keys on, so a
    baseline survives a flow minting a new record (which is the normal case);
    `display_label` carries the record id for the human-readable report.
    """
    targets: list[tuple[str, str, Path]] = []
    for label, flow_dir, gds_name in DEFAULT_TARGETS:
        pointer = repo_root / flow_dir / "reports" / "LATEST"
        if not pointer.is_file():
            raise MeasurementError(f"no reports/LATEST pointer at {pointer}")
        record = pointer.read_text().strip()
        gds = repo_root / flow_dir / "reports" / record / gds_name
        if not gds.is_file():
            raise MeasurementError(f"{pointer} -> {record}, but no {gds_name} in that record")
        targets.append((label, f"{label} [{record}]", gds))
    return targets


# --------------------------------------------------------------------------- #
# Baseline grading (issue #338) -- pure bookkeeping, no KLayout, unit-tested
# headlessly in sim/tests/test_metal_min_area_baseline.py.
# --------------------------------------------------------------------------- #
def load_baseline(path: Path) -> dict:
    """Read and validate a baseline file, or raise `MeasurementError` (exit 2)."""
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise MeasurementError(f"no baseline file at {path}") from exc
    except json.JSONDecodeError as exc:
        raise MeasurementError(f"{path}: not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise MeasurementError(f"{path}: baseline must be a JSON object")
    if raw.get("schema") != BASELINE_SCHEMA:
        raise MeasurementError(
            f"{path}: expected \"schema\": \"{BASELINE_SCHEMA}\", got {raw.get('schema')!r}"
        )
    allowances = raw.get("allowances")
    if not isinstance(allowances, list):
        raise MeasurementError(f"{path}: \"allowances\" must be a list")

    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(allowances):
        where = f"{path}: allowances[{i}]"
        if not isinstance(entry, dict):
            raise MeasurementError(f"{where}: must be an object")
        for field in BASELINE_REQUIRED_FIELDS:
            if field not in entry:
                raise MeasurementError(f"{where}: missing required field {field!r}")
        for field in ("target", "rule", "tracking_issue", "reason"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise MeasurementError(f"{where}: {field!r} must be a non-empty string")
        count = entry["max_below_min_area"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise MeasurementError(
                f"{where}: 'max_below_min_area' must be a non-negative integer, got {count!r}"
            )
        key = (entry["target"], entry["rule"])
        if key in seen:
            raise MeasurementError(f"{where}: duplicate allowance for {key[0]!r} rule {key[1]!r}")
        seen.add(key)

    return raw


def apply_baseline(results: list[dict], baseline: dict | None) -> dict:
    """Grade measured results against the baseline's per-(target, rule) ceilings.

    With `baseline=None` every allowance is 0, i.e. any shape below threshold
    is an exceedance -- the plain measurement's own semantics.

    Returns a verdict dict with three disjoint findings:

      `exceeded`  more shapes than allowed  -> failure (exit 1)
      `stale`     fewer shapes than allowed -> pass, but the allowance should
                  be tightened or deleted (it has outlived its finding)
      `unknown`   an allowance whose (target, rule) was not measured at all
                  -> usage error (exit 2): a typo'd or rotted waiver key must
                  never read as "nothing to waive, all good"
    """
    allowances = {
        (entry["target"], entry["rule"]): entry for entry in (baseline or {}).get("allowances", [])
    }

    measured: dict[tuple[str, str], int] = {}
    for result in results:
        for layer in result["layers"]:
            measured[(result["target"], layer["rule"])] = layer["below_min_area"]

    exceeded, stale, waived = [], [], []
    for key in sorted(measured):
        target, rule = key
        count = measured[key]
        entry = allowances.get(key)
        allowed = entry["max_below_min_area"] if entry else 0
        finding = {
            "target": target,
            "rule": rule,
            "below_min_area": count,
            "allowed": allowed,
            "tracking_issue": entry["tracking_issue"] if entry else None,
        }
        if count > allowed:
            exceeded.append(finding)
        elif entry is not None and count < allowed:
            stale.append(finding)
        elif entry is not None and count == allowed and allowed > 0:
            waived.append(finding)

    unknown = [
        {"target": target, "rule": rule}
        for (target, rule) in sorted(allowances)
        if (target, rule) not in measured
    ]

    return {
        "exceeded": exceeded,
        "stale": stale,
        "waived": waived,
        "unknown_allowances": unknown,
        "measured_total": sum(measured.values()),
        "allowed_total": sum(
            entry["max_below_min_area"]
            for key, entry in allowances.items()
            if key in measured
        ),
        "over_allowance_total": sum(f["below_min_area"] - f["allowed"] for f in exceeded),
    }


#: The flow the `--self-test` negative control pretends its illegal fixture
#: came from. It is deliberately one of the three whose geometry this repo
#: hand-authors end to end and which measure 0 today -- so the self-test also
#: fails if somebody ever adds an allowance for it to the baseline file.
SELF_TEST_TARGET = "cdac-array"


def self_test(rules: list[dict], baseline: dict | None) -> bool:
    """Prove the gate is reachable: does one isolated sub-minimum pad fail it?

    A clean verdict means nothing until "fails" is shown reachable on the same
    rules in the same run -- the falsifiability discipline this repo applies to
    every other layout verdict (see layout/*/README.md's negative-control
    verdicts 3/6/10/11). So this builds a deliberately-illegal fixture -- ONE
    isolated square on the met3 layer, sized from the deck's own `m3.6`
    threshold rather than any transcribed number, so its area is below it --
    measures it with the same `measure_gds` the real targets go through, and
    grades it through the same `apply_baseline` against the REAL baseline
    while claiming to be `cdac-array`. That is, literally: a newly-introduced
    isolated sub-minimum-area shape in one of this repo's own hand-authored
    flows must turn the gate red.

    Returns True if the gate caught it.
    """
    import math
    import tempfile

    try:
        import klayout.db as kdb
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MeasurementError(
            "the `klayout` python module is not importable -- run this from "
            "this repo's own layout venv (layout/bin/setup-venv.sh)"
        ) from exc

    rule = next((r for r in rules if r["symbol"] == "m3"), None)
    if rule is None:
        raise MeasurementError("deck carries no m3 minimum-area rule to build a fixture against")

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("min_area_negative_control")
    li = layout.layer(rule["layer"], rule["datatype"])
    # Half the side of a square that would exactly meet the threshold, so the
    # fixture's area is a quarter of it -- unambiguously below, on any deck.
    side_um = math.sqrt(rule["min_area_um2"]) / 2.0
    side_dbu = int(round(side_um / layout.dbu))
    top.shapes(li).insert(kdb.Box(0, 0, side_dbu, side_dbu))

    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "min_area_negative_control.gds"
        layout.write(str(fixture))
        result = measure_gds(fixture, rules)

    result["target"] = SELF_TEST_TARGET
    verdict = apply_baseline([result], baseline)
    caught = [
        f
        for f in verdict["exceeded"]
        if f["target"] == SELF_TEST_TARGET
        and f["rule"] == rule["rule"]
        and f["below_min_area"] == 1
        and f["allowed"] == 0
    ]

    area_um2 = side_um * side_um
    print("Negative control (issue #338): one isolated met3 square of")
    print(
        f"  {side_um:.3f} x {side_um:.3f} um = {area_um2:.4f} um2, below "
        f"{rule['rule']}'s {rule['min_area_um2']} um2, attributed to {SELF_TEST_TARGET!r}"
    )
    if caught:
        print(f"  GATE FAILS AS IT MUST: {caught[0]['rule']} 1 shape > allowance 0")
        return True
    print(
        "  GATE DID NOT FAIL -- the minimum-area measurement is vacuous as configured "
        f"(is there an allowance for {SELF_TEST_TARGET!r} in the baseline?)",
        file=sys.stderr,
    )
    return False


def _warn(message: str) -> None:
    """Print a warning, as a GitHub Actions annotation when running in CI."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=metal minimum area::{message}")
    print(f"WARNING: {message}", file=sys.stderr)


def report_baseline(verdict: dict, baseline_path: Path) -> None:
    """Print the human-readable baseline section of the report."""
    print(f"\nBaseline: {baseline_path}")
    for finding in verdict["waived"]:
        print(
            f"  waived   {finding['target']} {finding['rule']}: "
            f"{finding['below_min_area']} shape(s), allowance "
            f"{finding['allowed']} ({finding['tracking_issue']})"
        )
    for finding in verdict["stale"]:
        _warn(
            f"STALE ALLOWANCE: {finding['target']} {finding['rule']} now measures "
            f"{finding['below_min_area']} shape(s), below its allowance of "
            f"{finding['allowed']} ({finding['tracking_issue']}). The finding this "
            f"allowance was written for has shrunk or closed -- tighten the entry, or "
            f"delete it if it is now zero."
        )
    for finding in verdict["exceeded"]:
        print(
            f"  FAIL     {finding['target']} {finding['rule']}: "
            f"{finding['below_min_area']} shape(s) below minimum area, "
            f"allowance {finding['allowed']}"
        )
    if not verdict["exceeded"]:
        print(
            f"  OK: {verdict['measured_total']} shape(s) below threshold, all within "
            f"the recorded allowances ({verdict['allowed_total']})"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure sky130A's met1-met5 minimum-area rules against a GDS."
    )
    parser.add_argument("gds", nargs="*", type=Path, help="GDS files to measure")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="grade against per-(target, rule) allowances from this baseline file",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "negative control: measure a deliberately-illegal fixture and exit non-zero "
            "unless the gate flags it (proves a clean verdict is not vacuous)"
        ),
    )
    parser.add_argument("--pdk-root", type=Path, default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root used to resolve the default targets",
    )
    args = parser.parse_args(argv)

    try:
        pdk_root = args.pdk_root or Path(os.environ.get("PDK_ROOT", "~/.volare")).expanduser()
        variant = args.variant or os.environ.get("PDK", "sky130A")
        deck = find_deck(Path(pdk_root).expanduser(), variant)
        rules = parse_min_area_rules(deck.read_text())

        baseline = load_baseline(args.baseline) if args.baseline else None

        if args.self_test:
            print(f"PDK deck: {deck}")
            return 0 if self_test(rules, baseline) else 1

        if args.gds:
            targets = [(str(p), str(p), p) for p in args.gds]
            for _, _, path in targets:
                if not path.is_file():
                    raise MeasurementError(f"no such GDS: {path}")
        else:
            targets = resolve_default_targets(args.repo_root.resolve())

        results = [
            dict(measure_gds(path, rules), target=key, label=label) for key, label, path in targets
        ]

        verdict = apply_baseline(results, baseline)
        if verdict["unknown_allowances"]:
            unknown = ", ".join(
                f"{u['target']!r}/{u['rule']}" for u in verdict["unknown_allowances"]
            )
            raise MeasurementError(
                f"{args.baseline}: allowance(s) for a target/rule that was not measured: "
                f"{unknown} -- a baseline key that matches nothing would silently waive "
                f"nothing; fix the key or delete the entry (--baseline grades the default "
                f"target set, so do not combine it with explicit GDS arguments)"
            )
    except MeasurementError as exc:
        print(f"measure_metal_min_area.py: {exc}", file=sys.stderr)
        return 2

    total = sum(r["total_below_min_area"] for r in results)
    failed = bool(verdict["exceeded"])

    if args.json:
        print(
            json.dumps(
                {
                    "pdk": {"root": str(pdk_root), "variant": variant, "deck": str(deck)},
                    "rules": rules,
                    "results": results,
                    "total_below_min_area": total,
                    "baseline": (
                        None
                        if baseline is None
                        else {"path": str(args.baseline), "verdict": verdict}
                    ),
                },
                indent=2,
            )
        )
        for finding in verdict["stale"]:
            _warn(
                f"STALE ALLOWANCE: {finding['target']} {finding['rule']} measures "
                f"{finding['below_min_area']} of an allowed {finding['allowed']} "
                f"({finding['tracking_issue']})"
            )
        return 1 if failed else 0

    print(f"PDK deck: {deck}")
    for result in results:
        print(f"\n{result['label']}")
        print(f"  GDS:  {result['gds']}  (top cell {result['top_cell']})")
        for layer in result["layers"]:
            print(
                f"  {layer['rule']:<8} {layer['symbol']} "
                f"({layer['layer']}/{layer['datatype']}): "
                f"{layer['merged_polygons']} merged polygons, "
                f"{layer['below_min_area']} below {layer['min_area_um2']} um2"
            )
            for shape in layer["shapes"]:
                x0, y0, x1, y1 = shape["bbox_um"]
                print(
                    f"      area {shape['area_um2']:.4f} um2  "
                    f"bbox ({x0:.3f}, {y0:.3f}) - ({x1:.3f}, {y1:.3f})  "
                    f"{shape['width_um']:.3f} x {shape['height_um']:.3f} um"
                )
        print(f"  subtotal: {result['total_below_min_area']} shape(s) below minimum area")

    print(f"\nTOTAL: {total} shape(s) below their metal's minimum area")

    if baseline is not None:
        report_baseline(verdict, args.baseline)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

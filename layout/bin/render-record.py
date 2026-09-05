#!/usr/bin/env python3
"""Render layout/trivial-cell/reports/<record-id>/record.md from the `klt`
JSON envelopes `run-trivial-cell-flow.sh` just produced in that directory.

Standard library only (matching sim/harness/'s no-extra-runtime-dependency
convention).

Exits non-zero -- *after* writing record.md, so the evidence trail still
carries a record of the failure -- if any of the six expected verdicts do not
hold:

  1. DRC clean on the known-good generated cell
  2. LVS "match" on the known-good reference
  3. LVS "mismatch" on the device-parameter negative control
  4. LVS "mismatch" on the topology negative control
  5. `klt draw` wrote the deliberately-illegal fixture
  6. DRC "violations" on that fixture, flagging the exact rule it violates

Verdicts 5-6 are this repo's addition over 2AMLogic/sky130-bandgap's
layout/bin/render-record.py (commit 1f04e8524cc2d8c2c7154773749b1b2d3be2ce64),
which this file is otherwise ported from per CLAUDE.md's "Harness bootstrap"
instruction: a DRC deck that matched no rules at all would satisfy verdict 1
forever, so "clean" only means something once "not clean" has been shown to be
reachable on the same deck in the same run.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record_common_strict import (  # noqa: E402
    build_argparser_strict,
    git_field,
    load_json_strict,
)

# The rule the injected fixture is built to violate. Asserted by name, not
# just by count: a nonzero violation_count from some *other* rule would prove
# the deck flags something, but not that it flags the geometry we planted.
EXPECTED_INJECTED_RULE = "diff.width.1"

_load = load_json_strict
_git = git_field


def main() -> int:
    ap = build_argparser_strict()
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    gen = _load(out_dir / "gen.json")
    drc = _load(out_dir / "drc.json")
    extract = _load(out_dir / "extract.json")
    lvs_good = _load(out_dir / "lvs.json")
    lvs_bad_dev = _load(out_dir / "lvs.broken-device.json")
    lvs_bad_topo = _load(out_dir / "lvs.broken-topology.json")
    draw = _load(out_dir / "draw.json")
    drc_injected = _load(out_dir / "drc.injected.json")

    sha = _git(args.repo_root, "rev-parse", "HEAD")
    branch = _git(args.repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(args.repo_root, "status", "--porcelain") != ""

    klt_version = subprocess.run(
        [args.klt, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    pdk_info = json.loads(
        subprocess.run(
            [args.klt, "pdk", "find", "--pdk", args.pdk_variant, "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    injected_rules = sorted(
        {v.get("rule") for v in drc_injected.get("violations", []) if v.get("rule")}
    )

    checks = [
        ("DRC on the generated known-good cell is clean", drc.get("status") == "clean"),
        ("LVS matches the known-good reference", lvs_good.get("status") == "match"),
        (
            "LVS negative control (device-parameter corruption) reports mismatch",
            lvs_bad_dev.get("status") == "mismatch",
        ),
        (
            "LVS negative control (topology corruption) reports mismatch",
            lvs_bad_topo.get("status") == "mismatch",
        ),
        (
            "the deliberately-illegal DRC fixture was written",
            draw.get("shape_count", 0) > 0,
        ),
        (
            "DRC negative control flags the injected "
            f"`{EXPECTED_INJECTED_RULE}` violation",
            drc_injected.get("status") == "violations"
            and EXPECTED_INJECTED_RULE in injected_rules,
        ),
    ]
    all_pass = all(ok for _, ok in checks)

    lines: list[str] = []
    a = lines.append
    a(f"# Layout DRC/LVS record: {args.record_id}")
    a("")
    a(
        "Trivial-cell proof of the `klt`-driven sky130 DRC/LVS flow (issue "
        "#2) -- **not** SAR ADC layout, which is a later issue's scope, and "
        "not a spec claim of any kind. This record substantiates exactly one "
        "thing: that the flow runs headlessly end to end *and* that both of "
        "its verdicts are falsifiable on this toolchain."
    )
    a("")
    a("## Overall verdict: " + ("PASS" if all_pass else "FAIL"))
    a("")
    for desc, ok in checks:
        a(f"- [{'x' if ok else ' '}] {desc}")
    a("")
    a("## Flow")
    a("")
    a(
        "1. `klt gen mos_array --pdk "
        f"{args.pdk_variant} --cell-name trivial_mos_array` "
        "-- generator defaults (2x2 array, 1 dummy column per side, nfet, no "
        "well drawn)."
    )
    a("2. `klt drc trivial_mos_array.gds --deck sky130` -- must be clean.")
    a("3. `klt extract trivial_mos_array.gds --deck sky130 --top trivial_mos_array`")
    a(
        "4. `klt lvs` against `reference.spice` (known-good) and two "
        "negative-control references (`reference.broken-device.spice`, "
        "`reference.broken-topology.spice`)."
    )
    a(
        "5. `klt draw --params drc_violation_fixture.json` -- writes a "
        "known-illegal shape verbatim, no rule checking."
    )
    a(
        "6. `klt drc drc_violation_fixture.gds --deck sky130` -- must NOT be "
        f"clean, and must name `{EXPECTED_INJECTED_RULE}`."
    )
    a("")
    a("## Cell")
    a("")
    a("- Generator: `mos_array` (`klt gen --list` for the full params schema)")
    a(f"- `device_count` (real, non-dummy): {gen.get('device_count')}")
    a(f"- bbox (um): {gen.get('bbox_um')}")
    a(f"- `matched_group_id`: {gen.get('drc_hints', {}).get('matched_group_id')}")
    a("")
    a("## Results")
    a("")
    a("| Stage | Status | Detail |")
    a("| --- | --- | --- |")
    a(
        "| DRC (known-good cell) | "
        f"{drc.get('status')} | violation_count={drc.get('violation_count')} |"
    )
    a(
        "| Extract | "
        f"{extract.get('status')} | device_count={extract.get('device_count')}, "
        f"net_count={extract.get('net_count')}, pin_count={extract.get('pin_count')} |"
    )
    a(
        "| LVS (good reference) | "
        f"{lvs_good.get('status')} | mismatch_count={lvs_good.get('mismatch_count')}, "
        f"category_counts={lvs_good.get('category_counts')} |"
    )
    a(
        "| LVS negative control: device parameter | "
        f"{lvs_bad_dev.get('status')} | mismatch_count={lvs_bad_dev.get('mismatch_count')}, "
        f"category_counts={lvs_bad_dev.get('category_counts')} |"
    )
    a(
        "| LVS negative control: topology (shorted net) | "
        f"{lvs_bad_topo.get('status')} | mismatch_count={lvs_bad_topo.get('mismatch_count')}, "
        f"category_counts={lvs_bad_topo.get('category_counts')} |"
    )
    a(
        "| DRC negative control: injected violation | "
        f"{drc_injected.get('status')} | "
        f"violation_count={drc_injected.get('violation_count')}, "
        f"rules={injected_rules} |"
    )
    a("")
    good_mismatches = lvs_good.get("mismatches", [])
    non_warning = [m for m in good_mismatches if m.get("severity") != "warning"]
    ambiguous_net = [
        m
        for m in good_mismatches
        if m.get("category") == "topology" and m.get("net") is not None
    ]
    unused_class = [
        m
        for m in good_mismatches
        if m.get("category") == "topology" and m.get("net") is None
    ]
    body_unverified = [
        m for m in good_mismatches if m.get("category") == "device.body_unverified"
    ]
    a(
        f"The good-reference LVS run's `mismatch_count` "
        f"({lvs_good.get('mismatch_count')}) is nonzero while `status` is "
        f'`"match"` -- all {len(good_mismatches)} entries are '
        f'`severity: "warning"` ({len(non_warning)} at `severity: "error"`; '
        "see `lvs.json`), and are documented, expected quirks of this minimal, "
        "fully symmetric cell:"
    )
    a(
        f"- `device.body_unverified` (x{len(body_unverified)}): the curated "
        "sky130 extraction deck draws no distinct NMOS substrate/tap layer, so "
        "every body terminal compares against a deck-synthesized `vsubs` net "
        "rather than a real schematic net (documented in `klt extract`'s own "
        '"Coverage" docs).'
    )
    a(
        f"- `topology`, ambiguous net pairing (x{len(ambiguous_net)}): the "
        "array's unit devices are electrically interchangeable (no two devices "
        "share a net that would anchor a unique pairing), so `NetlistComparer` "
        "resolves the correspondence structurally rather than uniquely -- "
        "expected for a fully symmetric matched array, not a defect."
    )
    a(
        f"- `topology`, unused device class on both sides (x{len(unused_class)}): "
        "device classes the sky130 deck can recognise (e.g. `pfet`, `pnp`, "
        "`resistor`) that this cell draws none of -- not a real mismatch."
    )
    if non_warning:
        a(
            f'- **{len(non_warning)} `severity: "error"` entries were present '
            "-- this is NOT a clean match and the assertion above should have "
            "failed.**"
        )
    a("")
    a("## Provenance")
    a("")
    a(f"- Record ID: `{args.record_id}`")
    a(f"- `klt` version: `{klt_version}` (pinned, see `layout/requirements.txt`)")
    a(
        "- KLayout engine version: "
        f"`{drc.get('provenance', {}).get('klayout_version')}`"
    )
    a(f"- PDK: `{pdk_info.get('variant')}`, `{pdk_info.get('version')}`")
    a(
        "- PDK pin cross-check: compare `version` above against "
        "`sim/pdk.json`'s `open_pdks_commit`. This flow does not itself "
        "enforce the pin (unlike `sim/run_corners.py --check-env`), so a "
        "mismatch here is a manual reproducibility note, not a hard failure."
    )
    a(f"- Repo state: `{sha}` on `{branch}`" + (" (dirty)" if dirty else " (clean)"))
    a("")
    a(
        "Append-only, same rule as `sim/`: a re-run mints a new record id "
        "under `layout/trivial-cell/reports/` rather than editing this one."
    )
    a("")
    a("## Links")
    a("")
    a("- [`gen.json`](gen.json), [`trivial_mos_array.gds`](trivial_mos_array.gds)")
    a("- [`drc.json`](drc.json)")
    a(
        "- [`extract.json`](extract.json), "
        "[`trivial_mos_array.extract.spice`](trivial_mos_array.extract.spice)"
    )
    a(
        "- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json), "
        "[`reference.spice`](reference.spice)"
    )
    a(
        "- [`lvs.broken-device.request.json`](lvs.broken-device.request.json), "
        "[`lvs.broken-device.json`](lvs.broken-device.json), "
        "[`reference.broken-device.spice`](reference.broken-device.spice)"
    )
    a(
        "- [`lvs.broken-topology.request.json`](lvs.broken-topology.request.json), "
        "[`lvs.broken-topology.json`](lvs.broken-topology.json), "
        "[`reference.broken-topology.spice`](reference.broken-topology.spice)"
    )
    a(
        "- [`drc_violation_fixture.json`](drc_violation_fixture.json), "
        "[`draw.json`](draw.json), "
        "[`drc_violation_fixture.gds`](drc_violation_fixture.gds), "
        "[`drc.injected.json`](drc.injected.json)"
    )
    a("- [`report.md`](report.md) -- combined `klt report --format github-summary`")
    a("")

    print("\n".join(lines))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

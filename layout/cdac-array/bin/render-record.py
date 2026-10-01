#!/usr/bin/env python3
"""Render layout/cdac-array/reports/<record-id>/record.md from the JSON
envelopes run-flow.sh already wrote into that directory, and *assert* this
sub-block's verdicts.

Mirrors layout/bin/render-record.py's discipline: every verdict is read out
of `klt`'s own JSON envelope, never inferred from a process exit code, and
the record is written whether the verdicts hold or not (a failing record is
evidence too). Exit status is 0 iff every verdict below holds, so
run-flow.sh can fail the run on a regression:

  1. `klt drc` reports **clean** on cdac_unit_cell
  2. `klt lvs` reports **match** on cdac_unit_cell
  3. `klt drc` reports **clean** on cdac_array
  4. `klt lvs` reports **match** on cdac_array
  5. `klt extract` finds exactly 1024 MiM unit capacitors + 18 nfet + 18 pfet
     in cdac_array. Since issue #148 (see README.md's "`options.combine_devices`
     -- issue #148"), verdict 4's own LVS comparison is already literal and
     uncombined -- it compares 1024 drawn unit capacitors against 1024
     reference unit cards 1:1, so it already fails if the array is not built
     from exactly 1024 identical unit elements. This verdict is therefore a
     redundant, but cheap and orthogonal, independent confirmation of the
     same fact on the extraction side alone -- not the load-bearing check it
     used to be back when LVS folded w parallel unit caps into one device
     before comparing (see README.md).
  6. The common-centroid placement actually holds: every weighted bit's
     unit-capacitor centroid sits exactly on the array's own centre in Y,
     bits 8..4 also in X, and each bit's P-side and N-side centroids
     coincide. This is the only verdict here that says anything at all about
     *matching*; DRC and LVS are silent about it, which is exactly why a
     wrong-but-plausible placement would otherwise pass unnoticed.
  7. `klt precheck` passes outright on BOTH grids, for both top cells: the
     layout's own 1 nm database grid AND sky130's 5 nm manufacturing grid.
     The 5 nm run is gating here, not advisory, per
     spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md:
     `klt drc`'s curated sky130 deck carries no `*.ongrid` rule on any layer,
     while the PDK's own shipped signoff deck runs `<layer>.ongrid(0.005)` by
     default on every metal/via layer this block draws -- so verdicts 1/3
     above are silent about grid legality and this one is the only thing that
     is not. It became passable only with DR-019's resize of `C_u` to a
     5 nm-legal 1.9000 um plate: on the previous 1.898 um plate this check
     reported 1 off-grid `capm` shape in `cdac_unit_cell` and 1024 in
     `cdac_array` (one per drawn unit), which is why the flow did not run it
     before #498.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "bin"))

from _record_common import (  # noqa: E402
    build_argparser,
    git_commit_and_dirty,
    load_json,
    resolve_pdk_commit,
    tool_version,
)

EXPECTED_ARRAY_DEVICES = {
    "sky130_fd_pr__model__cap_mim": 1024,
    "nfet": 18,
    "pfet": 18,
}


def _failing_checks(precheck: dict) -> list[str]:
    """Names of every `klt precheck` check that reported `fail`."""
    return sorted(
        str(check.get("name"))
        for check in precheck.get("checks", [])
        if check.get("status") == "fail"
    )


def _offgrid_census(precheck: dict) -> dict[tuple[str, str], int]:
    """`{(cell, layer): count}` for the `offgrid` check's own violations.

    Empty on a passing run. Kept (rather than reporting a bare count) so a
    future regression names the layer it is on, which is what decides whether
    it is a MiM-plate consequence or a routing defect -- the same census shape
    `layout/halflsb-offset/bin/render-record.py` renders.
    """
    census: dict[tuple[str, str], int] = {}
    for check in precheck.get("checks", []):
        if check.get("name") != "offgrid":
            continue
        for violation in check.get("violations", []):
            key = (str(violation.get("cell")), str(violation.get("layer")))
            census[key] = census.get(key, 0) + 1
    return census


def main() -> int:
    args = build_argparser().parse_args()

    draw = load_json(os.path.join(args.out_dir, "draw.json"))
    # The array's envelopes carry the flat names (it is this sub-block's
    # headline cell); the unit cell's are suffixed. See run-flow.sh.
    per_top = {
        top: {
            kind: load_json(
                os.path.join(
                    args.out_dir,
                    f"{kind}.json" if top == "cdac_array" else f"{kind}.{top}.json",
                )
            )
            for kind in ("drc", "extract", "lvs")
        }
        for top in ("cdac_unit_cell", "cdac_array")
    }
    # The two precheck envelopes follow the same flat/suffixed naming, with
    # the 5 nm run carrying an extra `.grid5` segment before `.json` (same
    # file names layout/halflsb-offset/ uses).
    precheck = {
        top: {
            grid: load_json(
                os.path.join(
                    args.out_dir,
                    (
                        f"precheck{grid_part}.json"
                        if top == "cdac_array"
                        else f"precheck.{top}{grid_part}.json"
                    ),
                )
            )
            for grid, grid_part in (("0.001", ""), ("0.005", ".grid5"))
        }
        for top in ("cdac_unit_cell", "cdac_array")
    }

    commit, dirty = git_commit_and_dirty(args.repo_root)

    verdicts: list[tuple[str, bool, str]] = []
    precheck_verdicts: list[tuple[str, bool, str]] = []
    lines: list[str] = []
    lines.append(f"# CDAC array layout record: {args.record_id}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- `klt` version: {tool_version(args.klt, '--version')}")
    lines.append(f"- xschem version: {tool_version('xschem', '--version')}")
    lines.append(
        f"- PDK: {args.pdk_variant} ({resolve_pdk_commit(args.klt, args.pdk_variant)})"
    )
    # `klt drc`/`klt extract`/`klt lvs` above are all invoked `--deck`-only (no
    # `--pdk`), so their own JSON envelopes stamp `provenance.pdk: null` --
    # this flow's `open_pdks` commit pin comes only from the independent
    # `resolve_pdk_commit()` line above (issue #407). Still print
    # `provenance.pdk` when a future `klt` build (or a flow change) populates
    # it, as a cheap cross-check against the resolution above.
    array_pdk = (per_top["cdac_array"]["extract"].get("provenance") or {}).get("pdk")
    if array_pdk and array_pdk.get("version"):
        lines.append(f"- extraction's own provenance.pdk: {array_pdk.get('name')} {array_pdk.get('version')}")
    lines.append(f"- repo commit: `{commit}`{' (dirty)' if dirty else ''}")
    lines.append("")

    array = draw.get("array") or {}
    lines.append("## Drawn geometry")
    lines.append(f"- unit capacitance (derived from the drawn plate): {draw.get('cap_unit_f')} F")
    lines.append(f"- unit capacitors drawn: {array.get('n_units')}")
    counts = array.get("unit_counts") or {}
    lines.append(
        "- units per bottom-plate net: "
        + ", ".join(f"`{net}`={counts[net]}" for net in sorted(counts))
    )
    lines.append("")

    for top in ("cdac_unit_cell", "cdac_array"):
        drc = per_top[top]["drc"]
        extract = per_top[top]["extract"]
        lvs = per_top[top]["lvs"]
        lines.append(f"## `{top}`")

        clean = drc.get("status") == "clean"
        verdicts.append((f"{top}: DRC clean", clean, str(drc.get("violation_count"))))
        if clean:
            lines.append(f"- DRC (sky130 deck): **CLEAN** ({drc.get('violation_count', 0)} violations)")
        else:
            lines.append(
                f"- DRC (sky130 deck): **{str(drc.get('status', 'not run')).upper()}** -- "
                f"{drc.get('violation_count', '?')} violations: {drc.get('rule_counts')}"
            )

        for grid, label in (
            ("0.001", "1 nm database grid"),
            ("0.005", "5 nm manufacturing grid"),
        ):
            env = precheck[top][grid]
            passed = env.get("status") == "pass"
            failing = _failing_checks(env)
            census = _offgrid_census(env)
            # Appended to `verdicts` only at the end of main(), so the
            # numbering README.md's own verdict table uses (1..8, predating
            # #498) stays stable and these land as 9..12.
            precheck_verdicts.append(
                (
                    f"{top}: precheck passes on the {label}",
                    passed,
                    f"failing checks {failing}" if failing else "all checks pass",
                )
            )
            lines.append(
                f"- precheck (--grid-um {grid}, {label}): "
                f"**{str(env.get('status', 'not run')).upper()}** -- "
                f"{len(env.get('checks', []))} checks, {len(failing)} failed"
            )
            for (cell, layer), count in sorted(census.items()):
                lines.append(f"  - off-grid: {count} shape(s) in `{cell}` on layer `{layer}`")

        lines.append(
            f"- extraction: {extract.get('device_count')} devices "
            f"{extract.get('device_counts')}, {extract.get('net_count')} nets, "
            f"{extract.get('pin_count')} pins"
        )
        if extract.get("warnings"):
            for warning in extract["warnings"]:
                lines.append(f"  - extraction warning: {warning}")

        matched = lvs.get("status") == "match"
        verdicts.append((f"{top}: LVS match", matched, str(lvs.get("status"))))
        lvs_counts = lvs.get("counts") or {}
        lines.append(f"- LVS vs. `design/cdac/{top}.sch`: **{str(lvs.get('status', 'not run')).upper()}**")
        if lvs_counts:
            lines.append(
                f"  - devices: layout={lvs_counts.get('devices', {}).get('layout')} "
                f"reference={lvs_counts.get('devices', {}).get('reference')} "
                f"matched={lvs_counts.get('devices', {}).get('matched')}"
            )
            lines.append(
                f"  - nets: layout={lvs_counts.get('nets', {}).get('layout')} "
                f"reference={lvs_counts.get('nets', {}).get('reference')} "
                f"matched={lvs_counts.get('nets', {}).get('matched')}"
            )
        hard = [m for m in lvs.get("mismatches", []) if m.get("severity") != "warning"]
        for m in hard[:10]:
            lines.append(f"  - mismatch: {m.get('category')} ({m.get('side')}): {m.get('description')}")
        lines.append("")

    got = per_top["cdac_array"]["extract"].get("device_counts") or {}
    unit_elements_ok = got == EXPECTED_ARRAY_DEVICES
    verdicts.append(("cdac_array: 1024 unit caps + 18 nfet + 18 pfet extracted", unit_elements_ok, str(got)))
    lines.append("## Unit-element check")
    lines.append(
        "Since issue #148, `klt lvs`'s own comparison (verdict 4, above) is "
        "already literal and uncombined -- it compares this array's 1024 "
        "drawn unit capacitors against 1024 reference unit cards 1:1, with "
        "no `combine_devices` folding on either side, so an LVS match alone "
        "already implies the array is built from exactly 1024 unit elements. "
        "This is therefore a redundant, but cheap and independent, "
        "confirmation of the same fact from the extraction side alone:"
    )
    lines.append(f"- expected: `{EXPECTED_ARRAY_DEVICES}`")
    lines.append(f"- extracted: `{got}` -- **{'OK' if unit_elements_ok else 'MISMATCH'}**")
    lines.append("")

    # --- centroid / common-centroid verdict ---------------------------------
    cents = array.get("centroids") or {}
    tol = 1e-6
    lines.append("## Common-centroid check")
    lines.append(
        "Per-net unit-capacitor centroid, in um, relative to the array's own "
        "geometric centre. A linear process gradient across the array is "
        "cancelled exactly when a bit's centroid sits on that centre; a "
        "differential gradient between the two sides is cancelled when a "
        "bit's P and N centroids coincide."
    )
    lines.append("")
    lines.append("| net | units | dx (um) | dy (um) |")
    lines.append("| --- | ---: | ---: | ---: |")
    for net in sorted(cents, key=lambda s: (s.split("_")[-1], s)):
        e = cents[net]
        lines.append(f"| `{net}` | {e['n']} | {e['dx_um']:+.3f} | {e['dy_um']:+.3f} |")
    lines.append("")

    zero_y = [f"BOT_{s}{i}" for i in range(1, 9) for s in ("p", "n")]
    zero_x = [f"BOT_{s}{i}" for i in range(4, 9) for s in ("p", "n")]
    y_ok = cents and all(abs(cents[n]["dy_um"]) < tol for n in zero_y if n in cents)
    x_ok = cents and all(abs(cents[n]["dx_um"]) < tol for n in zero_x if n in cents)
    pn_x_ok = cents and all(
        abs(cents[f"BOT_p{i}"]["dx_um"] - cents[f"BOT_n{i}"]["dx_um"]) < tol
        for i in range(0, 9)
        if f"BOT_p{i}" in cents
    )
    verdicts.append(("bits 8..1: Y centroid on the array centre", bool(y_ok), "|dy| < 1e-6 um"))
    verdicts.append(("bits 8..4: X centroid on the array centre", bool(x_ok), "|dx| < 1e-6 um"))
    verdicts.append(("bits 8..0: P and N X centroids coincide", bool(pn_x_ok), "|dx_p - dx_n| < 1e-6 um"))
    lines.append(
        "Residuals, all of them deliberate and documented in "
        "`layout/cdac-array/README.md`: bit3 and the bit2/bit1/bit0/"
        "termination group each own a single, unsplittable column, so their "
        "X centroids sit half a column pitch either side of the centre "
        "(equal and opposite, so the *side total* is still centred); and "
        "bit0 and the termination unit are single units per side, so their "
        "P/N pair is one row pitch apart in Y rather than coincident."
    )
    lines.append("")

    verdicts.extend(precheck_verdicts)

    lines.append("## Manufacturing-grid check")
    lines.append(
        "`klt precheck --grid-um 0.005` is a **gating** verdict for this "
        "block, not an advisory metric, per "
        "`spec/decision-records/DR-019-cdac-unit-cap-grid-legal-plate-resize.md`. "
        "The reason it has to be is that nothing else in this flow checks it: "
        "`klt drc`'s curated `sky130` deck carries no `*.ongrid` rule on any "
        "layer (its own `rules_checked`/`rules_skipped` lists have no OFFGRID "
        "entry), while the PDK's own shipped signoff deck "
        "(`$PDK_ROOT/sky130A/libs.tech/klayout/drc/sky130A.lydrc`, "
        "`OFFGRID = true`) runs `<layer>.ongrid(0.005)` by default on every "
        "metal/via layer this block draws. A DRC-clean verdict above is "
        "therefore silent about grid legality; this one is not."
    )
    lines.append("")
    lines.append(
        "This check only became passable with DR-019. On the pre-#498 "
        "`CAPM_SIDE = 1.898` plate (1898 nm, not a multiple of 5) the same "
        "command reported 1 off-grid `capm` (89/44) shape in `cdac_unit_cell` "
        "and 1024 in `cdac_array` -- one per drawn unit, every one of them the "
        "plate itself. DR-019's resize to 1.9000 um puts every plate edge on "
        "both grids, and with it every coordinate this flow derives from a "
        "plate edge."
    )
    lines.append("")

    lines.append("## Verdicts")
    for name, ok, detail in verdicts:
        lines.append(f"- [{'x' if ok else ' '}] {name} ({detail})")
    lines.append("")
    lines.append(
        "Matching quality is **not** among the verdicts above and cannot be: "
        "DRC and LVS are silent about it. See `layout/cdac-array/README.md` "
        "for the common-centroid/dummy strategy this layout implements, what "
        "it cancels, and what it does not."
    )

    print("\n".join(lines))
    return 0 if all(ok for _, ok, _ in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())

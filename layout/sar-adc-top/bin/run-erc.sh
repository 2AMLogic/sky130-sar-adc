#!/usr/bin/env bash
# layout/sar-adc-top/bin/run-erc.sh -- the T1 item 11 (Power delivery,
# structural) run for this block: `klt erc` against the top-level assembly
# GDS, driven by layout/sar-adc-top/erc-supply-spec.json, recorded as a
# timestamped, append-only report under
# layout/sar-adc-top/erc-reports/<record-id>/ (issue #344).
#
# Usage:
#   layout/bin/setup-erc-venv.sh              # once, or after an erc-requirements.txt bump
#   layout/sar-adc-top/bin/run-erc.sh         # ~1 s; grades reports/LATEST's GDS
#   layout/sar-adc-top/bin/run-erc.sh <gds>   # grade a specific GDS instead
#
# Deliberately a SEPARATE report tree from layout/sar-adc-top/reports/. That
# tree's records are minted by run-flow.sh and each holds one full
# place/route/DRC/extract/LVS pass; an ERC record holds a verdict ABOUT one of
# those records' GDS files and regenerates none of it. Writing into an
# existing record would mutate committed evidence (CLAUDE.md: `sim/`- and
# `layout/`-style results are append-only -- a later run mints a new record
# rather than overwriting an earlier one), and minting a reports/<id>/ record
# with no layout in it would misrepresent what that tree means.
#
# Runs on layout/.venv-erc (klayout-tools==0.6.0, layout/erc-requirements.txt),
# NOT on the DRC/LVS flow's layout/.venv (0.5.0) -- see erc-requirements.txt's
# header for the whole justification, and note that the supply verdict itself
# is identical on both builds (cross-checked in each record's record.md).
set -euo pipefail

PROG="$(basename "${BASH_SOURCE[0]}")"
BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv-erc/bin/klt"
SPEC="$BLOCK_DIR/erc-supply-spec.json"
ERC_REPORTS="$BLOCK_DIR/erc-reports"

# shellcheck source=../../bin/_flow_common.sh
source "$LAYOUT_DIR/bin/_flow_common.sh"

if [[ ! -x "$KLT" ]]; then
  echo "$PROG: $KLT not found -- run layout/bin/setup-erc-venv.sh first" >&2
  exit 1
fi

# Input: an explicit GDS, or the one layout/sar-adc-top/reports/LATEST names.
if [[ -n "${1:-}" ]]; then
  GDS="$1"
else
  LATEST_ID="$(cat "$BLOCK_DIR/reports/LATEST")"
  GDS="$BLOCK_DIR/reports/$LATEST_ID/sar_adc_top.gds"
fi
if [[ ! -f "$GDS" ]]; then
  echo "$PROG: no such layout: $GDS" >&2
  exit 1
fi

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$ERC_REPORTS/$RECORD_ID"
mkdir -p "$OUT_DIR"

echo "$PROG: klt $("$KLT" --version | awk '{print $2}')"
echo "$PROG: layout $GDS"
echo "$PROG: spec   $SPEC"

# `klt erc` exits 3 when it completed successfully AND found ERC findings --
# a real verdict, not a failure to run, so it must not trip `set -e`. Exit 1
# (could not run: bad spec, unreadable layout) still must.
set +e
"$KLT" erc "$GDS" "$SPEC" --pdk sky130 --deck sky130 --format json \
  >"$OUT_DIR/erc.json" 2>"$OUT_DIR/erc.stderr"
RC=$?
set -e
if [[ "$RC" != 0 && "$RC" != 3 ]]; then
  echo "$PROG: klt erc failed (exit $RC):" >&2
  cat "$OUT_DIR/erc.stderr" >&2
  exit "$RC"
fi
[[ -s "$OUT_DIR/erc.stderr" ]] || rm -f "$OUT_DIR/erc.stderr"

# Self-check: the report is only evidence if it is pinned to the artefacts it
# was actually run against. Assert both hashes here rather than leaving a
# reader to re-derive them -- a report whose input hash has drifted from the
# committed GDS is stale, and staleness is failure (docs/t1-gap.md).
python3 - "$OUT_DIR/erc.json" "$GDS" "$SPEC" <<'PY'
import hashlib, json, sys

report_path, gds_path, spec_path = sys.argv[1:4]
report = json.load(open(report_path))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


prov = report.get("provenance")
if not prov:
    sys.exit(
        "run-erc.sh: this klt build's `klt erc` writes no provenance block -- "
        "see layout/erc-requirements.txt for why the pin must carry one"
    )
for label, got, want in (
    ("input (layout)", prov["input"]["content_hash"], sha256(gds_path)),
    ("spec", prov["spec"]["content_hash"], sha256(spec_path)),
):
    if got != want:
        sys.exit(f"run-erc.sh: {label} content-hash mismatch: {got} != {want}")

findings = report.get("erc_findings", [])
supplies = {n["name"] for n in json.load(open(spec_path)).get("nets", [])}
blocking = [
    f
    for f in findings
    if f["rule"] in ("erc.unconnected_net", "erc.supply_short", "erc.missing_tie")
    and (f.get("net") in supplies or f.get("other_net") in supplies)
]
print(f"run-erc.sh: content-hashes verified (layout + spec)")
print(f"run-erc.sh: erc_status={report.get('erc_status')} findings={len(findings)}")
print(
    "run-erc.sh: T1 item 11 verdict: "
    + ("MET" if not blocking else f"UNMET ({len(blocking)} blocking finding(s))")
)
for f in blocking:
    print(f"run-erc.sh:   {f['rule']}: {f['description']}")
PY

echo "$RECORD_ID" >"$ERC_REPORTS/LATEST"
echo "$PROG: wrote $OUT_DIR/erc.json (erc-reports/LATEST -> $RECORD_ID)"
echo "$PROG: write $OUT_DIR/record.md by hand -- the verdict narrative is not generated"

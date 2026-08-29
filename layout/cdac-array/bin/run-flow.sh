#!/usr/bin/env bash
# layout/cdac-array/bin/run-flow.sh -- generate the differential CDAC array
# sub-block's layout (issue #100) and run it through DRC/extract/LVS,
# recording a timestamped, append-only report under
# layout/cdac-array/reports/<record-id>/, mirroring
# layout/trivial-cell/reports/'s own convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                  # once, or after bumping requirements.txt
#   source sim/env.sh                          # exports PDK_ROOT/PDK for xschem
#   layout/cdac-array/bin/run-flow.sh          # ~6 seconds
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and `xschem` on $PATH (the LVS
# reference is regenerated from design/cdac/*.sch, never hand-authored --
# see bin/generate-lvs-reference.py).
#
# Flow, per top cell (cdac_unit_cell, then cdac_array):
#   bin/cdac_layout.py  -> the GDS  (a repo-local generator on `klayout.db`,
#                          calling the pinned `klt gen mos_array` for the two
#                          switch devices)
#   klt drc             -> drc.json
#   klt extract         -> extract.json + <top>.extract.spice
#   klt lvs             -> lvs.json      (against the schematic-derived
#                          reference regenerated in step 0)
#
# Verdicts: this script asserts DRC **clean** and LVS **match** for both top
# cells and exits non-zero if either fails. Unlike layout/sar-sequencer's
# flow it has no "expected blocker" carve-out -- this sub-block's acceptance
# criteria (issue #100) require both verdicts outright, so a regression must
# fail the run rather than be recorded as a known state.
#
# `set -e` is deliberately suspended around the `klt drc`/`klt lvs`
# invocations: a bad verdict is exit 3, a normal *documented* outcome that
# this script reads out of the JSON envelope rather than off the exit code
# (the same discipline layout/bin/run-trivial-cell-flow.sh applies, and for
# the same reason -- the envelope names *which* rule fired, the exit code
# only says something did).
set -euo pipefail

CDAC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$CDAC_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PY="$LAYOUT_DIR/.venv/bin/python"
PDK_VARIANT=sky130A
TOPS=(cdac_unit_cell cdac_array)

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"
if ! command -v xschem >/dev/null 2>&1; then
  echo "run-flow.sh: no 'xschem' on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$CDAC_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 0. Regenerate the LVS references from the schematics -------------------
# Always regenerated, never trusted from the committed copy: an LVS "match"
# is only worth something if the reference provably still says what
# design/cdac/*.sch says today.
"$PY" "$CDAC_DIR/bin/generate-lvs-reference.py"

# --- 1. Draw ----------------------------------------------------------------
"$PY" "$CDAC_DIR/bin/cdac_layout.py" \
  --unit-cell-out "$OUT_DIR/cdac_unit_cell.gds" \
  --array-out "$OUT_DIR/cdac_array.gds" \
  --summary-out "$OUT_DIR/draw.json"

for TOP in "${TOPS[@]}"; do
  GDS="$OUT_DIR/${TOP}.gds"
  cp "$CDAC_DIR/reference/${TOP}.lvs-reference.spice" "$OUT_DIR/${TOP}.lvs-reference.spice"
  # The array is this sub-block's headline cell, so *its* envelopes take the
  # flat `drc.json`/`extract.json`/`lvs.json` names the trivial-cell record
  # convention calls for; the unit cell's are suffixed. (Writing both and
  # then copying would duplicate a ~280 kB extraction envelope inside every
  # committed record for no added evidence.)
  if [[ "$TOP" == "cdac_array" ]]; then SUFFIX=""; else SUFFIX=".${TOP}"; fi

  # --- 2. DRC ---------------------------------------------------------------
  set +e
  "$KLT" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc${SUFFIX}.json"
  set -e

  # --- 3. Extract -----------------------------------------------------------
  set +e
  "$KLT" extract "$GDS" --deck sky130 --format json \
    -o "$OUT_DIR/${TOP}.extract.spice" > "$OUT_DIR/extract${SUFFIX}.json"
  set -e

  # --- 4. LVS ---------------------------------------------------------------
  cat > "$OUT_DIR/lvs${SUFFIX}.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "${TOP}.gds",
    "deck": "sky130",
    "top": "${TOP}",
    "top_cell_pins": true
  },
  "reference": {
    "netlist": "${TOP}.lvs-reference.spice",
    "top": "${TOP}"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
  set +e
  "$KLT" lvs "$OUT_DIR/lvs${SUFFIX}.request.json" --format json > "$OUT_DIR/lvs${SUFFIX}.json"
  set -e
done

# --- 5. Record + verdict assertions -----------------------------------------
# `set -e` off here on purpose: render-record.py exits 1 when a verdict
# fails, and the record it just wrote is the evidence of *why* -- aborting
# before the LATEST pointer is updated would throw that away.
set +e
"$PY" "$CDAC_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" > "$OUT_DIR/record.md"
status=$?
set -e

echo "$RECORD_ID" > "$CDAC_DIR/reports/LATEST"
if [[ $status -ne 0 ]]; then
  echo "run-flow.sh: VERDICTS FAILED -- see $OUT_DIR/record.md" >&2
  exit "$status"
fi
echo "run-flow.sh: done. See $OUT_DIR/record.md"

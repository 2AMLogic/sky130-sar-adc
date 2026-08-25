#!/usr/bin/env bash
# layout/comparator/bin/run-flow.sh -- draw the dynamic comparator sub-block
# (issue #101) via `klt gen` + `klt gen-compose`, then run it through
# DRC/extract/LVS, recording a timestamped, append-only report under
# layout/comparator/reports/<record-id>/, mirroring
# layout/trivial-cell/reports/'s and layout/sar-sequencer/reports/'s own
# convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   source sim/env.sh                  # exports PDK_ROOT/PDK
#   layout/comparator/bin/run-flow.sh  # ~1 minute
#
# Flow: `klt gen` x5 (one per matched device/pair, see gen_blocks.py's own
# "Matching strategy" docstring) -> `klt gen-compose` (place + route into one
# cell, see build_compose_request.py) -> `klt drc` -> `klt extract` -> `klt
# lvs` against reference.spice (hand-authored, cross-checked against
# design/comparator.sch's own device list -- see that file's header).
#
# Composition status (see README.md "Composition status" for the full,
# honest writeup): this script always runs every stage and records whatever
# verdict each one reports -- it does not assume any particular outcome, so a
# rerun against a future klt release closes the gap documented in README.md
# will simply record cleaner verdicts without any script change. `set -e` is
# deliberately not applied to gen-compose/drc/lvs (a non-clean verdict is a
# normal documented outcome here, not a script failure -- matching
# run-trivial-cell-flow.sh's/sar-sequencer's own convention).
set -uo pipefail

COMPARATOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$COMPARATOR_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0

if [[ ! -x "$KLT" ]]; then
  echo "run-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$COMPARATOR_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Generate the five matched-device/pair blocks -----------------------
if ! python3 "$COMPARATOR_DIR/bin/gen_blocks.py" "$OUT_DIR" --klt "$KLT" --pdk "$PDK_VARIANT"; then
  echo "run-flow.sh: gen_blocks.py FAILED" >&2
  echo "$RECORD_ID" > "$COMPARATOR_DIR/reports/LATEST"
  exit 1
fi

# --- 2. Compose (place + route) ---------------------------------------------
python3 "$COMPARATOR_DIR/bin/build_compose_request.py" -o "$OUT_DIR/compose.request.json"
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
compose_status=$?
echo "run-flow.sh: gen-compose exit=$compose_status (3 == partial success, see compose.json)"
GDS="$OUT_DIR/${TOP}.gds"
if [[ ! -f "$GDS" ]]; then
  echo "run-flow.sh: gen-compose did not write $GDS -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$COMPARATOR_DIR/reports/LATEST"
  exit 1
fi
mv "$GDS" "$OUT_DIR/comparator.gds"
GDS="$OUT_DIR/comparator.gds"

# --- 3. DRC against the sky130 deck -----------------------------------------
"$KLT" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc.json"

# --- 4. Extract -------------------------------------------------------------
"$KLT" extract "$GDS" --deck sky130 --top "$TOP" --format json > "$OUT_DIR/extract.json"

# --- 5. LVS: layout (extracted inline) vs. the hand-authored reference ------
cp "$COMPARATOR_DIR/reference.spice" "$OUT_DIR/reference.spice"
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "comparator.gds",
    "deck": "sky130",
    "top": "${TOP}",
    "top_cell_pins": true
  },
  "reference": {
    "netlist": "reference.spice",
    "top": "comparator"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
( cd "$OUT_DIR" && "$KLT" lvs lvs.request.json --format json > lvs.json )

# --- 6. Record summary --------------------------------------------------
python3 "$COMPARATOR_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" > "$OUT_DIR/record.md"

echo "$RECORD_ID" > "$COMPARATOR_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"

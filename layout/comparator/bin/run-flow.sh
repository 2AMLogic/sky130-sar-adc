#!/usr/bin/env bash
# layout/comparator/bin/run-flow.sh -- draw, place, route and verify the
# dynamic comparator sub-block (issue #101), recording a timestamped,
# append-only report under layout/comparator/reports/<record-id>/, mirroring
# layout/trivial-cell/reports/'s and layout/sar-sequencer/reports/'s own
# convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh            # once, or after bumping requirements.txt
#   layout/comparator/bin/run-flow.sh   # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json; `volare enable --pdk sky130 <sha>`).
#
# Flow:
#   1. `klt gen` x6      -- one matched device/pair block per schematic device
#                           group (see gen_blocks.py's "Matching strategy").
#   2. `klt drc` x6      -- each block on its own must be clean before it is
#                           allowed into the composition.
#   3. build_layout.py   -- floorplan + route: emits the `klt draw` request for
#                           every wire and the `klt gen-compose` placement.
#   4. `klt draw`        -- writes the routing/tap/well cell verbatim.
#   5. `klt gen-compose` -- places the six blocks + the routing cell at
#                           explicit origins. No `routing` block: this flow
#                           does its own routing (see build_layout.py's
#                           docstring for why).
#   6. `klt drc`         -- the composed layout must be CLEAN.
#   7. `klt extract`     -- schematic-equivalent netlist + body-tie check.
#   8. `klt lvs` x3      -- must MATCH reference.spice, and must MISMATCH both
#                           deliberately corrupted references (device-parameter
#                           corruption, topology corruption). A "match" verdict
#                           means nothing until "mismatch" is shown reachable on
#                           the same toolchain in the same run -- the same
#                           falsifiability discipline layout/trivial-cell/'s own
#                           six-verdict flow established for this repo.
#
# Exit codes: 0 every verdict held, 1 at least one flipped (the record is still
# written first, so the evidence trail keeps the failure).
#
# `klt drc` exits 3 when it finds violations and `klt lvs` exits 3 on a
# mismatch (klt reserves 3 for "ran fine, verdict was bad" and 1 for "did not
# run"). A 3 is the EXPECTED outcome of the negative-control stages, so every
# verdict-bearing invocation is `|| true`-guarded and the verdict is asserted
# from the JSON envelope by render-record.py, never from an exit code.
set -euo pipefail

COMPARATOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$COMPARATOR_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0
BLOCKS=(tail inpair latn latp rst rstd)

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$COMPARATOR_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Generate the six matched-device/pair blocks ------------------------
python3 "$COMPARATOR_DIR/bin/gen_blocks.py" "$OUT_DIR" --klt "$KLT" --pdk "$PDK_VARIANT"

# --- 2. Per-block DRC: every input block must be clean in isolation ---------
# Recorded as one envelope keyed by block id, so a later composed-DRC failure
# can be attributed to the routing rather than to a device block.
{
  echo '{'
  sep=''
  for block in "${BLOCKS[@]}"; do
    printf '%s  "%s": ' "$sep" "$block"
    "$KLT" drc "$OUT_DIR/$block.gds" --deck sky130 --format json || true
    sep=$',\n'
  done
  echo '}'
} > "$OUT_DIR/drc.blocks.json"

# --- 3. Floorplan + route ---------------------------------------------------
python3 "$COMPARATOR_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 4. Draw every wire, tap and well shape --------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name ROUTE \
    -o route.gds --format json > draw.json )

# --- 5. Place the blocks + the routing cell into one composed cell ----------
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$COMPARATOR_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/comparator.gds"

# --- 6. DRC on the composed layout: must be CLEAN --------------------------
( cd "$OUT_DIR" && "$KLT" drc comparator.gds --deck sky130 --format json > drc.json ) || true

# --- 7. Extract a schematic-equivalent netlist ------------------------------
( cd "$OUT_DIR" && "$KLT" extract comparator.gds --deck sky130 --top "$TOP" \
    -o comparator.extract.spice --format json > extract.json )

# --- 8. LVS: known-good reference (must report "match") --------------------
# `top_cell_pins` is deliberately left at its default (false): every pin label
# this flow draws lives in the instanced ROUTE cell, and the seven nets the
# reference declares as ports are exactly the seven labels drawn there.
for kind in "" ".broken-device" ".broken-topology"; do
  cp "$COMPARATOR_DIR/reference${kind}.spice" "$OUT_DIR/reference${kind}.spice"
  cat > "$OUT_DIR/lvs${kind}.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "comparator.gds", "deck": "sky130", "top": "${TOP}" },
  "reference": { "netlist": "reference${kind}.spice", "top": "comparator" },
  "options": { "combine_devices": true }
}
EOF
  ( cd "$OUT_DIR" && "$KLT" lvs "lvs${kind}.request.json" --format json \
      > "lvs${kind}.json" ) || true
done

# --- 9. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" "$OUT_DIR/lvs.json" \
  --format github-summary > "$OUT_DIR/report.md"

# --- 10. Record summary (pass/fail verdicts, evidence-record style) --------
set +e
python3 "$COMPARATOR_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$COMPARATOR_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"
exit "$record_status"

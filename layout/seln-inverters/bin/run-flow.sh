#!/usr/bin/env bash
# layout/seln-inverters/bin/run-flow.sh -- place-and-route the SELn<i> =
# NOT(DOUT<i>) inverter bank (issue #103's own new top-level glue logic --
# see netlist/seln_inverters.v's header for why this belongs to the
# integration issue rather than any sub-block) and run it through DRC/LVS,
# recording a timestamped, append-only report under
# layout/seln-inverters/reports/<record-id>/, mirroring
# layout/sar-sequencer/reports/'s own convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                     # once, or after bumping requirements.txt
#   source sim/env.sh                             # exports PDK_ROOT/PDK
#   layout/seln-inverters/bin/run-flow.sh          # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and an `openroad` binary on $PATH
# (`klt place-and-route` invokes it as a subprocess -- see
# docs/environment-setup.md).
#
# Flow (identical shape to layout/sar-sequencer/bin/run-flow.sh, minus its
# clock-tree-specific steps -- this design is purely combinational, so a
# nominal clock_port/clock_period_ns is declared only to satisfy
# `klt place-and-route`'s own request schema, per requests/place-and-route.json's
# comment): `klt place-and-route` -> `klt drc` -> post-route netlist dump ->
# generate-lvs-reference.py -> `klt extract --def-pins` -> `klt lvs`.
set -euo pipefail

BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=seln_inverters

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR/.klt/place-and-route"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Place-and-route -----------------------------------------------------
cp "$BLOCK_DIR/netlist/seln_inverters.v" "$OUT_DIR/seln_inverters.v"
sed "s#../netlist/seln_inverters.v#seln_inverters.v#" \
  "$BLOCK_DIR/requests/place-and-route.json" > "$OUT_DIR/place-and-route.json"

set +e
"$KLT" place-and-route "$OUT_DIR/place-and-route.json" --format json \
  > "$OUT_DIR/pnr.json" 2> "$OUT_DIR/pnr.stderr.log"
pnr_status=$?
set -e
if [[ $pnr_status -ne 0 ]]; then
  echo "run-flow.sh: place-and-route FAILED -- see $OUT_DIR/pnr.stderr.log" >&2
  cat "$OUT_DIR/pnr.json" >&2 || true
  echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"
  exit 1
fi

cp "$OUT_DIR/.klt/place-and-route/${TOP}.gds" "$OUT_DIR/${TOP}.gds"
cp "$OUT_DIR/.klt/place-and-route/${TOP}.def" "$OUT_DIR/${TOP}.def"
GDS="$OUT_DIR/${TOP}.gds"

# --- 2. DRC against the sky130 deck -----------------------------------------
"$KLT" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 3. Dump the post-route gate-level netlist ------------------------------
cat > "$OUT_DIR/.klt/place-and-route/dump_netlist.tcl" <<EOF
read_db ${TOP}_route.odb
write_verilog ${TOP}_post_route.v
EOF
( cd "$OUT_DIR/.klt/place-and-route" && openroad -no_init -exit dump_netlist.tcl \
  > "$OUT_DIR/dump_netlist.stdout.log" 2>&1 )
cp "$OUT_DIR/.klt/place-and-route/${TOP}_post_route.v" "$OUT_DIR/${TOP}_post_route.v"

# --- 4. Generate the LVS reference from the post-route netlist --------------
python3 "$BLOCK_DIR/bin/generate-lvs-reference.py" "$OUT_DIR/${TOP}_post_route.v"
REFERENCE_SRC="$BLOCK_DIR/reference/seln_inverters.lvs-reference.spice"
cp "$REFERENCE_SRC" "$OUT_DIR/seln_inverters.lvs-reference.spice"

# --- 5. Extract, deriving the declared pin set from the routed DEF ---------
"$KLT" extract "$GDS" --deck sky130 --top "$TOP" --def-pins "$OUT_DIR/${TOP}.def" \
  -o "$OUT_DIR/${TOP}.extract.spice" --format json > "$OUT_DIR/extract.json" || true

# --- 6. LVS: pre-extracted layout netlist vs. the generated reference -------
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "netlist": "${TOP}.extract.spice",
    "top": "${TOP}"
  },
  "reference": {
    "netlist": "seln_inverters.lvs-reference.spice",
    "top": "${TOP}"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

# --- 7. Record summary --------------------------------------------------
python3 "$BLOCK_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" > "$OUT_DIR/record.md"

# --- 8. Prune the .klt/ scratch cache ---------------------------------------
rm -rf "$OUT_DIR/.klt"

echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"

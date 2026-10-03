#!/usr/bin/env bash
# layout/top-glue/bin/run-flow.sh -- place-and-route the SAR ADC's top-level
# standard-cell glue bank (the 33 `sky130_fd_sc_hd` instances
# design/sar_adc_top.spice adds at the integration level, inside no sub-block
# -- see netlist/top_glue.v's header) and run it through DRC/LVS, recording a
# timestamped, append-only report under
# layout/top-glue/reports/<record-id>/, mirroring
# layout/sar-sequencer/reports/'s own convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
#   source sim/env.sh                     # exports PDK_ROOT/PDK
#   layout/top-glue/bin/run-flow.sh       # ~2 minutes
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and an `openroad` binary on $PATH
# (`klt place-and-route` invokes it as a subprocess -- see
# docs/environment-setup.md).
#
# Flow (identical shape to the superseded layout/seln-inverters/bin/
# run-flow.sh, with ONE step added at the front):
#   0. check-schematic-parity.py -- HARD GATE, and the whole reason this
#      block exists. Asserts netlist/top_glue.v is instance-for-instance,
#      net-for-net identical to design/sar_adc_top.spice's own top-level
#      sky130_fd_sc_hd instance lines. `klt lvs` below CANNOT establish this:
#      its reference is generated from the same netlist the layout is built
#      from, so the compare is self-consistent rather than checked against
#      the schematic -- which is exactly how issue #56's DR-008-superseded
#      glue survived two weeks of clean DRC/LVS runs (issue #387).
#   1. `klt place-and-route` (OpenROAD)
#   2. `klt drc --deck sky130`
#   3. post-route netlist dump (OpenROAD `write_verilog`)
#   4. generate-lvs-reference.py (flatten against the PDK's own CDL)
#   5. `klt extract --def-pins`
#   6. `klt lvs`
#   7. record.md
#
# Exit codes: 0 on success; 1 if the schematic-parity gate fails or
# place-and-route fails. DRC/LVS verdicts are recorded from their own JSON
# envelopes by render-record.py, never asserted from an exit code (matching
# every other flow in this directory).
set -euo pipefail

BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=top_glue

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

# --- 0. Schematic parity: the independent anchor (issue #387) ---------------
# Deliberately BEFORE the record directory is created: a netlist that has
# drifted from the schematic must not mint a record at all, so no future
# reader can cite a DRC/LVS verdict over geometry built from the wrong
# topology.
python3 "$BLOCK_DIR/bin/check-schematic-parity.py"

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR/.klt/place-and-route"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

python3 "$BLOCK_DIR/bin/check-schematic-parity.py" \
  > "$OUT_DIR/schematic-parity.txt" 2>&1

# --- 1. Place-and-route -----------------------------------------------------
cp "$BLOCK_DIR/netlist/${TOP}.v" "$OUT_DIR/${TOP}.v"
sed "s#../netlist/${TOP}.v#${TOP}.v#" \
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

# --- 3b. Re-run the parity gate on the POST-ROUTE netlist -------------------
# The pre-route gate above proves the hand-written netlist matches the
# schematic; this one proves the router did not add, drop or rename an
# instance on the way to the GDS the LVS reference is generated from.
python3 "$BLOCK_DIR/bin/check-schematic-parity.py" \
  --netlist "$OUT_DIR/${TOP}_post_route.v" \
  >> "$OUT_DIR/schematic-parity.txt" 2>&1

# --- 4. Generate the LVS reference from the post-route netlist --------------
python3 "$BLOCK_DIR/bin/generate-lvs-reference.py" "$OUT_DIR/${TOP}_post_route.v"
REFERENCE_SRC="$BLOCK_DIR/reference/${TOP}.lvs-reference.spice"
cp "$REFERENCE_SRC" "$OUT_DIR/${TOP}.lvs-reference.spice"

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
    "netlist": "${TOP}.lvs-reference.spice",
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

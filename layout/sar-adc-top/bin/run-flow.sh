#!/usr/bin/env bash
# layout/sar-adc-top/bin/run-flow.sh -- place, route and verify the
# top-level SAR ADC assembly (issue #103), recording a timestamped,
# append-only report under layout/sar-adc-top/reports/<record-id>/,
# mirroring layout/trivial-cell/reports/'s own convention (see
# layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/sar-adc-top/bin/run-flow.sh   # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and each of the five sub-blocks'
# reports/LATEST to point at a real, already-committed record (#99-#102,
# #166) -- this flow *reads* those GDS files, it does not regenerate them.
#
# Flow (see layout/sar-adc-top/README.md for the full floorplan/routing
# writeup this implements):
#   1. Copy each sub-block's own reports/LATEST top GDS in as this flow's
#      own input (named <block>.gds -- what build_layout.py's own
#      `blocks[].cell` request entries expect).
#   2. build_layout.py    -- floorplan + route: emits the `klt draw` request
#                            for every wire/via/label this assembly's own
#                            interconnect needs, and the `klt gen-compose`
#                            explicit-placement request naming all five
#                            sub-blocks (as `blocks[].cell` entries, #1189)
#                            plus this script's own new `route` cell.
#   3. `klt draw`          -- writes the routing cell verbatim.
#   4. `klt gen-compose`   -- places the five sub-blocks + the routing cell
#                            into one composed cell. No `routing` block:
#                            this flow does its own routing (see
#                            build_layout.py's docstring for why).
#   5. `klt drc`           -- the composed layout must be CLEAN.
#   6. `klt extract` (unfiltered) -- a full-hierarchy extraction with no
#      declared-pin restriction, used only to *verify connectivity by net*
#      (every intended net's own device membership, checked by hand against
#      the intended schematic -- see record.md) -- not a `klt lvs` input.
#   7. `klt extract --def-pins` + `klt lvs` -- the actual signoff attempt,
#      using a synthetic DEF naming this design's own 19 external ports.
#      Currently BLOCKED: see record.md and klayout-tools#1513 (filed by
#      this issue) for why no available `klt extract` pin-declaration mode
#      reproducibly promotes exactly this design's own intended top-level
#      port set once composed without a governing top-level DEF.
#
# Exit codes: 0 if DRC is clean (this flow's own current hard gate -- LVS is
# recorded whatever it reports, per klayout-tools#1513, not asserted here);
# 1 otherwise. `klt drc` exits 3 on violations found (not "did not run"), so
# it is `|| true`-guarded and the verdict is asserted from the JSON envelope
# by render-record.py, never from an exit code (matching every other flow in
# this directory).
set -euo pipefail

TOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$TOP_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$TOP_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Pull in each sub-block's own reports/LATEST top GDS ----------------
declare -A BLOCK_GDS=(
  [cdac_array]="cdac-array/cdac_array.gds"
  [sampling_frontend]="sampling-frontend/sampling_frontend.gds"
  [comparator]="comparator/comparator.gds"
  [sar_sequencer]="sar-sequencer/sar_sequencer.gds"
  [seln_inverters]="seln-inverters/seln_inverters.gds"
)
for block in "${!BLOCK_GDS[@]}"; do
  rel="${BLOCK_GDS[$block]}"
  subdir="${rel%%/*}"
  fname="${rel#*/}"
  latest="$(cat "$LAYOUT_DIR/$subdir/reports/LATEST")"
  cp "$LAYOUT_DIR/$subdir/reports/$latest/$fname" "$OUT_DIR/${block}.gds"
done

# --- 2. Floorplan + route ---------------------------------------------------
python3 "$TOP_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 3. Draw every wire, via and label --------------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name ROUTE \
    -o route.gds --format json > draw.json )

# --- 4. Place the five sub-blocks + the routing cell into one composed cell
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$TOP_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/sar_adc_top.gds"
GDS="$OUT_DIR/sar_adc_top.gds"

# --- 5. DRC on the composed layout: must be CLEAN --------------------------
"$KLT" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 6. Unfiltered extraction: connectivity verification, not an LVS input -
"$KLT" extract "$GDS" --deck sky130 --top "$TOP" \
    -o "$OUT_DIR/sar_adc_top.extract.unfiltered.spice" --format json \
    > "$OUT_DIR/extract.unfiltered.json" || true

# --- 7. Signoff attempt: synthetic DEF-derived declared pins + LVS ---------
# See this design's own 19-port list in design/sar_adc_top.sym; the DEF
# below exists only to carry that name list through `--def-pins` (issue
# #1390's own mechanism) -- its geometry/UNITS/DIEAREA fields are
# placeholders, never read by the name-only scan `--def-pins` performs.
cat > "$OUT_DIR/sar_adc_top.pins.def" <<'EOF'
VERSION 5.8 ;
DESIGN sar_adc_top ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
PINS 19 ;
    - VINP ;
    - VINN ;
    - VDD ;
    - VREFP ;
    - VREFN ;
    - VCM ;
    - CLK ;
    - RST_B ;
    - DOUT9 ;
    - DOUT8 ;
    - DOUT7 ;
    - DOUT6 ;
    - DOUT5 ;
    - DOUT4 ;
    - DOUT3 ;
    - DOUT2 ;
    - DOUT1 ;
    - DOUT0 ;
    - BUSY ;
END PINS
END DESIGN
EOF
"$KLT" extract "$GDS" --deck sky130 --top "$TOP" \
    --def-pins "$OUT_DIR/sar_adc_top.pins.def" \
    -o "$OUT_DIR/sar_adc_top.extract.spice" --format json \
    > "$OUT_DIR/extract.json" || true

python3 "$TOP_DIR/bin/generate-lvs-reference.py" \
  --sar-sequencer-report "$LAYOUT_DIR/sar-sequencer/reports/$(cat "$LAYOUT_DIR/sar-sequencer/reports/LATEST")" \
  --seln-inverters-report "$LAYOUT_DIR/seln-inverters/reports/$(cat "$LAYOUT_DIR/seln-inverters/reports/LATEST")" \
  -o "$OUT_DIR/sar_adc_top.lvs-reference.spice"

cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "netlist": "sar_adc_top.extract.spice", "top": "$TOP" },
  "reference": { "netlist": "sar_adc_top.lvs-reference.spice", "top": "sar_adc_top" },
  "options": { "combine_devices": true, "flatten_reference": true }
}
EOF
( cd "$OUT_DIR" && "$KLT" lvs lvs.request.json --format json > lvs.json ) || true

# --- 8. Record summary -------------------------------------------------
set +e
python3 "$TOP_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$TOP_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"
exit "$record_status"

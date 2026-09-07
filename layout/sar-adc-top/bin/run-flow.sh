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
# `SAR_ADC_TOP_KLT` env override: step 7's `klt extract --pin-source-cells`
# flag (klayout-tools#1515) postdates `layout/requirements.txt`'s pinned
# `klayout-tools==0.4.0` -- PyPI has not published a release newer than
# 0.4.0 yet (checked 2026-09-07), so the pinned `layout/.venv/bin/klt` this
# script uses by default does NOT have the flag. Set `SAR_ADC_TOP_KLT` to a
# `klt` build from klayout-tools commit 2313dd0301b2dd90e4cad9a2cf1c62ff36d3a9b5
# (#1515) or later to run this flow for real until a qualifying PyPI release
# lands and `layout/requirements.txt` can bump to it -- see
# layout/sar-adc-top/README.md's "Provenance" section and
# layout/requirements.txt's own header for the full trace. Every other step
# (draw/gen-compose/drc/unfiltered-extract) is unaffected by this override
# and works identically on the pinned 0.4.0 build.
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
#   3. `klt draw`          -- writes the routing cell verbatim, named
#                            SAR_ADC_TOP_ROUTE (not the generic ROUTE every
#                            other `bin/build_layout.py` flow in this repo
#                            uses) so it never collides with `comparator`'s
#                            or `sampling_frontend`'s own internal ROUTE
#                            cell once all five GDS files are merged -- see
#                            "LVS pin declaration: resolved" in README.md.
#   4. `klt gen-compose`   -- places the five sub-blocks + the routing cell
#                            into one composed cell. No `routing` block:
#                            this flow does its own routing (see
#                            build_layout.py's docstring for why).
#   5. `klt drc`           -- the composed layout must be CLEAN.
#   6. `klt extract` (unfiltered) -- a full-hierarchy extraction with no
#      declared-pin restriction, used only to *verify connectivity by net*
#      (every intended net's own device membership, checked by hand against
#      the intended schematic -- see record.md) -- not a `klt lvs` input.
#   7. `klt extract --pin-source-cells route__SAR_ADC_TOP_ROUTE` + `klt lvs`
#      -- the actual signoff attempt. `--pin-source-cells` (klayout-tools#1515)
#      resolves this flow's own 19 external-pin labels (all drawn directly in
#      this step's own SAR_ADC_TOP_ROUTE cell, by position, not by name) to
#      real top-level pins and demotes everything else -- reaching exactly
#      19/19/19 promoted/reference/matched pins, closing klayout-tools#1513.
#      `klt lvs` itself still reports a mismatch, but for an unrelated,
#      newly-discovered reason: see record.md and README.md's "LVS device/
#      topology blocker" section.
#
# Exit codes: 0 if DRC is clean (this flow's own current hard gate -- LVS is
# recorded whatever it reports, per the still-open LVS device/topology
# blocker (see README.md), not asserted here); 1 otherwise. `klt drc` exits 3
# on violations found (not "did not run"), so it is `|| true`-guarded and the
# verdict is asserted from the JSON envelope by render-record.py, never from
# an exit code (matching every other flow in this directory).
set -euo pipefail

TOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$TOP_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="${SAR_ADC_TOP_KLT:-$LAYOUT_DIR/.venv/bin/klt}"
PDK_VARIANT=sky130A
TOP=gen_compose_0
ROUTE_CELL_NAME=SAR_ADC_TOP_ROUTE
# The literal cell name `klt gen-compose` gives this flow's own routing cell
# once merged into the composed GDS -- deterministic `"<block-id>__<cell-name>"`
# (docs/cli/gen-compose.md, issue #1189), not merge-order-dependent. The
# compose request below names this block "route".
ROUTE_CELL_QUALIFIED="route__${ROUTE_CELL_NAME}"

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
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name "$ROUTE_CELL_NAME" \
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

# --- 7. Signoff attempt: `--pin-source-cells` declared pins + LVS ----------
# `--pin-source-cells` (klayout-tools#1515) resolves this flow's own 19
# top-level pin labels -- every one of them drawn directly in this step's own
# SAR_ADC_TOP_ROUTE cell (built in step 3), at each label's own real
# position, never by name -- to the real net at that position, and demotes
# every other promoted pin. This closes klayout-tools#1513 (see
# README.md "LVS pin declaration: resolved"): it reaches exactly this
# design's own intended 19/19/19 promoted/reference/matched pin counts,
# where none of `--top-cell-pins`/`--pins`/`--def-pins` could. Requires a
# `klt` build with klayout-tools#1515 -- see the `SAR_ADC_TOP_KLT` note atop
# this file if `$KLT` predates it.
"$KLT" extract "$GDS" --deck sky130 --top "$TOP" \
    --pin-source-cells "$ROUTE_CELL_QUALIFIED" \
    -o "$OUT_DIR/sar_adc_top.extract.spice" --format json \
    > "$OUT_DIR/extract.json" || true

python3 "$TOP_DIR/bin/generate-lvs-reference.py" \
  --sar-sequencer-report "$LAYOUT_DIR/sar-sequencer/reports/$(cat "$LAYOUT_DIR/sar-sequencer/reports/LATEST")" \
  --seln-inverters-report "$LAYOUT_DIR/seln-inverters/reports/$(cat "$LAYOUT_DIR/seln-inverters/reports/LATEST")" \
  -o "$OUT_DIR/sar_adc_top.lvs-reference.spice"

# `combine_devices: true`: three of the five already-independently-verified
# sub-blocks (comparator, sar_sequencer, seln_inverters) need it to re-lump
# their own genuinely split/interleaved layout legs to match their own
# reference's lumped devices; the other two (cdac_array, sampling_frontend)
# need it FALSE (cdac_array to avoid klayout-tools#1497's parallel-cap
# combine nondeterminism; sampling_frontend has nothing to fold, so it is a
# no-op either way at that sub-block's own scope). `klt lvs`'s
# `options.combine_devices` is a single flag over the whole (flattened)
# compared netlist -- no per-subcircuit scoping exists -- so no single
# top-level setting can satisfy every already-independently-verified
# sub-block's own requirement simultaneously; `true` was measured to
# produce fewer, more analyzable mismatches (98) than `false` (2197). See
# README.md's "LVS device/topology blocker" section for the full trace;
# filed generically at 2AMLogic/klayout-tools#1552.
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

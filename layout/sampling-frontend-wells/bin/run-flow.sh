#!/usr/bin/env bash
# layout/sampling-frontend-wells/bin/run-flow.sh -- draw, place, route and
# verify the sampling front end's PFET set and its three isolated n-well
# body-tie domains (issue #122), recording a timestamped, append-only report
# under layout/sampling-frontend-wells/reports/<record-id>/, mirroring
# layout/comparator/reports/'s and layout/trivial-cell/reports/'s convention
# (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                        # once
#   source sim/env.sh                               # exports PDK_ROOT/PDK
#   layout/sampling-frontend-wells/bin/run-flow.sh  # ~30 s
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json). No standalone `klayout` binary is
# needed: every stage below runs through klt's headless `--engine curated`
# DRC (issue #149 retired the `--engine klayout --deck-file
# drc/nwell_isolation.drc` stages once klt 0.4.0's curated sky130 deck grew
# `nwell.width.1`/`nwell.space.1` -- see ../README.md's verdict table).
#
# Flow:
#   1. `klt gen` x9      -- one PFET block per schematic PFET (gen_blocks.py).
#   2. `klt drc` x9      -- each block clean in isolation before composition.
#   3. build_layout.py   -- floorplan, n-well partition, taps, routing.
#   4. `klt draw`        -- writes the well/tap/routing cell verbatim.
#   5. `klt gen-compose` -- places the nine blocks + that cell (placer only).
#   6. `klt drc`         -- curated sky130 deck on the composed layout: CLEAN
#                           -- this is now also the n-well isolation verdict,
#                           since the curated deck carries nwell.width.1/
#                           nwell.space.1 as of klt 0.4.0.
#   7. `klt drc`         -- the SAME curated deck against a deliberately
#                           illegal fixture (two n-well islands closer than
#                           `nwell.2a`'s minimum spacing): VIOLATIONS, naming
#                           `nwell.space.1` -- without which verdict 6 would
#                           be indistinguishable from a deck that matched
#                           nothing (see drc/nwell_violation_fixture.json).
#   8. `klt precheck`    -- layout hygiene + pin labels land on drawn metal.
#   9. `klt extract`     -- netlist + the body-tie verdicts (this is the one
#                           that answers #122's question directly).
#  10. `klt lvs` x3      -- MATCH against reference.spice, MISMATCH against
#                           both negative controls (body-tie corruption,
#                           device-parameter corruption).
#
# Exit codes: 0 every verdict held, 1 at least one flipped (the record is
# still written first, so the evidence trail keeps the failure).
#
# `klt drc` exits 3 when it finds violations and `klt lvs` exits 3 on a
# mismatch (klt reserves 3 for "ran fine, verdict was bad" and 1 for "did not
# run"). A 3 is the EXPECTED outcome of every negative-control stage, so each
# verdict-bearing invocation is `|| true`-guarded and the verdict is asserted
# from the JSON envelope by render-record.py, never from an exit code.
set -euo pipefail

WELLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$WELLS_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0
VIOLATION_FIXTURE="$WELLS_DIR/drc/nwell_violation_fixture.json"
BLOCKS=(sa_p se_p scp_p cmswp_p invp cmswp_n scp_n se_n sa_n)

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$WELLS_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Generate one block per schematic PFET ------------------------------
python3 "$WELLS_DIR/bin/gen_blocks.py" "$OUT_DIR" --klt "$KLT" --pdk "$PDK_VARIANT"

# --- 2. Per-block DRC: every input block must be clean in isolation ---------
# Recorded as one envelope keyed by block id, so a later composed-DRC failure
# can be attributed to the routing/wells rather than to a device block.
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

# --- 3. Floorplan, n-well partition, taps, routing -------------------------
python3 "$WELLS_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 4. Draw the wells, taps and every wire --------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name ROUTE \
    -o route.gds --format json > draw.json )

# --- 5. Place the blocks + the well/routing cell ---------------------------
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$WELLS_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/sampling_frontend_pwells.gds"

# --- 6. Curated-deck DRC on the composed layout: must be CLEAN -------------
# As of klt 0.4.0 this is also the n-well isolation verdict: the curated
# sky130 deck carries nwell.width.1/nwell.space.1 directly (issue #149), so a
# deliberately split well that violated nwell.2a's spacing would show up
# here without a second deck.
( cd "$OUT_DIR" && "$KLT" drc sampling_frontend_pwells.gds --deck sky130 \
    --format json > drc.json ) || true

# --- 7. DRC negative control: the curated deck must FIRE on an illegal well
# split -------------------------------------------------------------------
# Two n-well islands closer than nwell.2a's 1.27 um minimum spacing --
# without this, "clean" above would be indistinguishable from a deck that
# matched nothing (the failure mode this sub-block's README used to record
# against klt 0.3.0's curated deck, which carried no n-well rules at all).
# See drc/nwell_violation_fixture.json's header.
cp "$VIOLATION_FIXTURE" "$OUT_DIR/nwell_violation_fixture.json"
( cd "$OUT_DIR" && "$KLT" draw --params nwell_violation_fixture.json \
    --cell-name NWELL_VIOLATION_FIXTURE -o nwell_violation_fixture.gds \
    --format json > draw.fixture.json )
( cd "$OUT_DIR" && "$KLT" drc nwell_violation_fixture.gds --deck sky130 \
    --format json > drc.curated.fixture.json ) || true

# --- 8. Layout hygiene + pin labels land on drawn metal --------------------
( cd "$OUT_DIR" && "$KLT" precheck sampling_frontend_pwells.gds --deck sky130 \
    --grid-um 0.005 --format json > precheck.json ) || true

# --- 9. Extract: the body-tie answer ---------------------------------------
( cd "$OUT_DIR" && "$KLT" extract sampling_frontend_pwells.gds --deck sky130 \
    --top "$TOP" -o sampling_frontend_pwells.extract.spice --format json \
    > extract.json )

# --- 10. LVS: one positive, two negative controls --------------------------
# `top_cell_pins` is deliberately left at its default (false): every pin label
# this flow draws lives in the instanced ROUTE cell, and the fourteen nets the
# reference declares as ports are exactly the fourteen labels drawn there.
for kind in "" ".broken-body-tie" ".broken-device"; do
  cp "$WELLS_DIR/reference${kind}.spice" "$OUT_DIR/reference${kind}.spice"
  cat > "$OUT_DIR/lvs${kind}.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "sampling_frontend_pwells.gds",
    "deck": "sky130",
    "top": "${TOP}"
  },
  "reference": {
    "netlist": "reference${kind}.spice",
    "top": "sampling_frontend_pwells"
  },
  "options": { "combine_devices": true }
}
EOF
  ( cd "$OUT_DIR" && "$KLT" lvs "lvs${kind}.request.json" --format json \
      > "lvs${kind}.json" ) || true
done

# --- 11. Combined human-readable report ------------------------------------
"$KLT" report "$OUT_DIR/drc.json" "$OUT_DIR/lvs.json" \
  --format github-summary > "$OUT_DIR/report.md"

# --- 12. Record summary (pass/fail verdicts, evidence-record style) --------
set +e
python3 "$WELLS_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$WELLS_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"
exit "$record_status"

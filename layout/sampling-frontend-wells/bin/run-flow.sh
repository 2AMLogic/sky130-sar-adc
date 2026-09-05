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
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK install
# (same pin as sim/pdk.json) and a `klayout` binary on PATH (the well-rule
# stages below run `klt drc --engine klayout`, which shells out to it).
#
# Flow:
#   1. `klt gen` x9      -- one PFET block per schematic PFET (gen_blocks.py).
#   2. `klt drc` x9      -- each block clean in isolation before composition.
#   3. build_layout.py   -- floorplan, n-well partition, taps, routing.
#   4. `klt draw`        -- writes the well/tap/routing cell verbatim.
#   5. `klt gen-compose` -- places the nine blocks + that cell (placer only).
#   6. `klt drc`         -- curated sky130 deck on the composed layout: CLEAN.
#   7. `klt drc` x2      -- the n-well rules the curated deck does NOT carry,
#                           via `--engine klayout --deck-file
#                           drc/nwell_isolation.drc`: CLEAN on the layout,
#                           VIOLATIONS on the deliberately-illegal fixture.
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
WELL_DECK="$WELLS_DIR/drc/nwell_isolation.drc"
BLOCKS=(sa_p se_p scp_p cmswp_p invp cmswp_n scp_n se_n sa_n)

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v klayout >/dev/null; then
  echo "run-flow.sh: no 'klayout' binary on PATH -- stage 7's n-well rules run" >&2
  echo "  through 'klt drc --engine klayout', which shells out to it." >&2
  exit 1
fi

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
( cd "$OUT_DIR" && "$KLT" drc sampling_frontend_pwells.gds --deck sky130 \
    --format json > drc.json ) || true

# --- 7. The n-well rules the curated deck does not carry -------------------
# Positive: the composed layout must be clean against nwell.1 / nwell.2a /
# difftap.8 / difftap.10.  Negative: the deliberately-illegal fixture must
# come back with violations naming those same rules -- without which "clean"
# above would be indistinguishable from a deck that matched nothing (exactly
# the failure mode `klt drc --deck sky130` has here).  See
# drc/nwell_isolation.drc's header.
cp "$WELL_DECK" "$OUT_DIR/nwell_isolation.drc"
cp "$WELLS_DIR/drc/nwell_isolation_fixture.json" "$OUT_DIR/nwell_isolation_fixture.json"
( cd "$OUT_DIR" && "$KLT" drc sampling_frontend_pwells.gds --engine klayout \
    --deck-file nwell_isolation.drc --format json > drc.wells.json ) || true
( cd "$OUT_DIR" && "$KLT" draw --params nwell_isolation_fixture.json \
    --cell-name NWELL_ISOLATION_FIXTURE -o nwell_isolation_fixture.gds \
    --format json > draw.fixture.json )
( cd "$OUT_DIR" && "$KLT" drc nwell_isolation_fixture.gds --engine klayout \
    --deck-file nwell_isolation.drc --format json > drc.wells.fixture.json ) || true
# The same fixture through the curated deck, recorded to make the gap itself
# reproducible evidence rather than a claim in a README.
( cd "$OUT_DIR" && "$KLT" drc nwell_isolation_fixture.gds --deck sky130 \
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

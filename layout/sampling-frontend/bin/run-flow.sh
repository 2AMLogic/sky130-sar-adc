#!/usr/bin/env bash
# layout/sampling-frontend/bin/run-flow.sh -- generate, floorplan, draw, place,
# route and verify the FULL sampling front end sub-block (issue #99), recording
# a timestamped, append-only report under
# layout/sampling-frontend/reports/<record-id>/, mirroring
# layout/comparator/reports/'s, layout/sampling-frontend-wells/reports/'s and
# layout/trivial-cell/reports/'s convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                  # once, or after bumping requirements.txt
#   source sim/env.sh                         # exports PDK_ROOT/PDK
#   layout/sampling-frontend/bin/run-flow.sh  # ~2 min
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json). Deliberately does NOT require a `klayout`
# binary on PATH: every stage below runs through klt's own built-in decks via
# the `klayout` Python module, unlike layout/sampling-frontend-wells/'s flow,
# which needed `klt drc --engine klayout --deck-file` to reach n-well rules the
# klt 0.3.0 curated deck did not carry. klt 0.4.0 carries them (see
# drc/nwell_rules_fixture.json's header), so that dependency is retired here.
#
# Flow:
#   1. `klt gen` x22     -- 9 PFET + 11 NFET `mos_array` singles and 2 `cap_array`
#                           matched pairs (gen_blocks.py).
#   2. `klt drc` x22     -- each block clean in isolation before composition, so
#                           a composed-DRC failure is attributable to the wells
#                           or the routing rather than to a device.
#   3. build_layout.py   -- floorplan, the three-island n-well partition, the
#                           substrate tap, and every wire.
#   4. `klt draw`        -- writes the well/tap/routing cell verbatim.
#   5. `klt gen-compose` -- places the 22 blocks + that cell (placer only).
#   6. `klt drc`         -- curated sky130 deck on the composed layout: CLEAN.
#   7. `klt draw`+`drc`  -- the deliberately-illegal n-well fixture through the
#                           SAME deck: VIOLATIONS naming nwell.space.1.
#   8. `klt precheck`    -- layout hygiene + pin labels land on drawn metal.
#   9. `klt extract`     -- netlist, device population, PMOS body terminals.
#  10. `klt lvs` x4      -- MATCH against reference.spice, MISMATCH against all
#                           three negative controls (body tie, device
#                           parameter, capacitor top-plate net).
#
# Exit codes: 0 every verdict held, 1 at least one flipped (the record is still
# written first, so the evidence trail keeps the failure).
#
# `klt drc` exits 3 when it finds violations and `klt lvs` exits 3 on a
# mismatch (klt reserves 3 for "ran fine, verdict was bad" and 1 for "did not
# run"). A 3 is the EXPECTED outcome of every negative-control stage, so each
# verdict-bearing invocation is `|| true`-guarded and the verdict is asserted
# from the JSON envelope by render-record.py, never from an exit code.
set -euo pipefail

SF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$SF_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0
DELIVERABLE=sampling_frontend.gds

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
OUT_DIR="$SF_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# The block-id list is derived from gen_blocks.py's own tables rather than
# duplicated here, so adding a device cannot silently escape the per-block DRC
# stage below.
# (`read -r` in a loop rather than `mapfile`, which macOS's system bash 3.2
# does not have.)
BLOCKS=()
while IFS= read -r block_id; do
  BLOCKS+=("$block_id")
done < <(python3 -c "
import sys; sys.path.insert(0, '$SF_DIR/bin')
from gen_blocks import PFET_DEVICES, NFET_DEVICES, CAP_DEVICES
for row in list(PFET_DEVICES) + list(NFET_DEVICES) + list(CAP_DEVICES):
    print(row[0])
")

# --- 1. Generate one block per schematic device ----------------------------
python3 "$SF_DIR/bin/gen_blocks.py" "$OUT_DIR" --klt "$KLT" --pdk "$PDK_VARIANT"

# --- 2. Per-block DRC: every input block must be clean in isolation ---------
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
python3 "$SF_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 4. Draw the wells, taps and every wire --------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name ROUTE \
    -o route.gds --format json > draw.json )

# --- 5. Place the blocks + the well/routing cell ---------------------------
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$SF_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/$DELIVERABLE"

# --- 6. Curated-deck DRC on the composed layout: must be CLEAN -------------
( cd "$OUT_DIR" && "$KLT" drc "$DELIVERABLE" --deck sky130 \
    --format json > drc.json ) || true

# --- 7. DRC negative control: the illegal n-well fixture, SAME deck --------
# Without this, "clean" above would be indistinguishable from a deck that
# matched nothing on the well layer -- which is exactly what klt 0.3.0's
# curated deck did (see drc/nwell_rules_fixture.json's header).
cp "$SF_DIR/drc/nwell_rules_fixture.json" "$OUT_DIR/nwell_rules_fixture.json"
( cd "$OUT_DIR" && "$KLT" draw --params nwell_rules_fixture.json \
    --cell-name NWELL_RULES_FIXTURE -o nwell_rules_fixture.gds \
    --format json > draw.fixture.json )
( cd "$OUT_DIR" && "$KLT" drc nwell_rules_fixture.gds --deck sky130 \
    --format json > drc.fixture.json ) || true

# --- 8. Layout hygiene + pin labels land on drawn metal --------------------
( cd "$OUT_DIR" && "$KLT" precheck "$DELIVERABLE" --deck sky130 \
    --grid-um 0.005 --format json > precheck.json ) || true

# --- 9. Extract ------------------------------------------------------------
( cd "$OUT_DIR" && "$KLT" extract "$DELIVERABLE" --deck sky130 \
    --top "$TOP" -o sampling_frontend.extract.spice --format json \
    > extract.json )

# --- 10. LVS: one positive, three negative controls ------------------------
# `top_cell_pins` is deliberately left at its default (false): every pin label
# this flow draws lives in the instanced ROUTE cell.
#
# `combine_devices` is deliberately FALSE. This sub-block instantiates no
# parallel devices for the option to fold (each of the 24 devices is distinct
# in the schematic), so it has nothing to do here -- while KLayout's own
# Netlist.combine_devices() is known to hit an internal-consistency error on
# partial-match device groups and leave a netlist half-combined (klt's own
# `device.combine_incomplete` warning, klayout-tools#1185). Enabling an option
# with no work to do, whose failure mode is a nondeterministic verdict, would
# be trading evidence quality for nothing.
for kind in "" ".broken-body-tie" ".broken-device" ".broken-topology"; do
  cp "$SF_DIR/reference${kind}.spice" "$OUT_DIR/reference${kind}.spice"
  cat > "$OUT_DIR/lvs${kind}.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "${DELIVERABLE}",
    "deck": "sky130",
    "top": "${TOP}"
  },
  "reference": {
    "netlist": "reference${kind}.spice",
    "top": "sampling_frontend"
  },
  "options": { "combine_devices": false }
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
python3 "$SF_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$SF_DIR/reports/LATEST"
if [[ "$record_status" -ne 0 ]]; then
  echo "run-flow.sh: VERDICTS FAILED -- see $OUT_DIR/record.md" >&2
else
  echo "run-flow.sh: done. See $OUT_DIR/record.md"
fi
exit "$record_status"

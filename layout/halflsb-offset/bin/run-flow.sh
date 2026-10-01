#!/usr/bin/env bash
# layout/halflsb-offset/bin/run-flow.sh -- generate, floorplan, draw, place and
# verify DR-009's half-LSB quantizer-offset network (issue #495), recording a
# timestamped, append-only report under
# layout/halflsb-offset/reports/<record-id>/, the same convention every sibling
# under layout/ follows (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                 # once, or after bumping requirements.txt
#   source sim/env.sh                        # exports PDK_ROOT/PDK
#   layout/halflsb-offset/bin/run-flow.sh    # ~1 min
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json). No `klayout` binary on PATH and no
# `openroad`: every stage runs through klt's own built-in decks via the
# `klayout` Python module.
#
# Flow:
#   0. parity gate        -- bin/check-schematic-parity.py, BEFORE the record
#                            directory exists, so a layout table that has
#                            drifted from design/sar_adc_top.spice cannot mint a
#                            record at all.
#   1. `klt gen` x7       -- 6 mos_array switch singles + 1 cap_array matched
#                            pair (gen_blocks.py).
#   2. `klt drc` x7       -- each block clean in isolation, so a composed-DRC
#                            failure is attributable to the wells or the routing
#                            rather than to a device.
#   3. build_layout.py    -- floorplan, two n-well islands, four taps, every
#                            wire; asserts the _n/_p translation congruence.
#   4. `klt draw`         -- writes the well/tap/routing cell verbatim.
#   5. `klt gen-compose`  -- places the 7 blocks + that cell (placer only).
#   6. `klt drc`          -- curated sky130 deck on the composed layout: CLEAN.
#   7. `klt draw`+`drc`   -- the deliberately-illegal n-well fixture through the
#                            SAME deck: VIOLATIONS naming nwell.space.1.
#   8. `klt precheck` x2  -- once on the layout's own 1 nm database grid and
#                            once on sky130's 5 nm manufacturing grid. BOTH
#                            must now pass outright: DR-019/#498 resized the
#                            MiM plate to a grid-legal 1.9000 um and the 5 nm
#                            census went 48 -> 0, so verdict 6 was inverted
#                            from "the residual is confined to the MiM stack"
#                            to "there is no residual" (see README, "The 5 nm
#                            manufacturing grid").
#   9. `klt extract`      -- netlist, device population, PMOS body terminals.
#  10. reference x4       -- bin/generate-lvs-reference.py, the schematic-derived
#                            good reference plus three negative controls.
#  11. `klt lvs` x4       -- MATCH against the good reference, MISMATCH against
#                            the device-parameter and capacitor top-plate
#                            controls, and -- the documented blind spot -- MATCH
#                            against the swapped-enable control, whose corruption
#                            shows up in the net-correspondence table instead.
#
# Exit codes: 0 every verdict held, 1 at least one flipped (the record is still
# written first, so the evidence trail keeps the failure).
#
# `klt drc` exits 3 when it finds violations and `klt lvs` exits 3 on a
# mismatch (klt reserves 3 for "ran fine, verdict was bad" and 1 for "did not
# run"). A 3 is the EXPECTED outcome of two of the LVS stages and of the DRC
# fixture, so each verdict-bearing invocation is `|| true`-guarded and the
# verdict is asserted from the JSON envelope by render-record.py, never from an
# exit code.
set -euo pipefail

HLO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$HLO_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0
DELIVERABLE=halflsb_offset.gds

# The n-well DRC negative control is layout/sampling-frontend/'s committed
# fixture, read in place rather than copied here. It is a deliberately illegal
# pair of n-well islands 0.50 um apart plus an under-width stripe -- nothing
# about it is specific to that sub-block, and this block needs exactly the same
# statement for exactly the same reason (its own n-well is split into two
# separately-drawn islands, so "DRC clean" says nothing about the split unless
# the deck can flag an illegal one). Duplicating the JSON would give this repo
# two copies of one fixture to keep in step.
NWELL_FIXTURE="$LAYOUT_DIR/sampling-frontend/drc/nwell_rules_fixture.json"

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if [[ ! -f "$NWELL_FIXTURE" ]]; then
  echo "run-flow.sh: DRC negative-control fixture missing: $NWELL_FIXTURE" >&2
  exit 1
fi

# --- 0. Schematic parity, before anything else -----------------------------
# Deliberately NOT `|| true`: a layout table that no longer matches
# design/sar_adc_top.spice must not be able to mint a record, so this is the one
# stage that aborts the flow instead of being graded afterwards. The record then
# re-states the verdict from the captured output, so a reader of the record does
# not have to take the flow's word for it.
PARITY_LOG="$(mktemp)"
trap 'rm -f "$PARITY_LOG"' EXIT
set +e
python3 "$HLO_DIR/bin/check-schematic-parity.py" > "$PARITY_LOG" 2>&1
parity_status=$?
set -e
cat "$PARITY_LOG"
if [[ "$parity_status" -ne 0 ]]; then
  echo "run-flow.sh: schematic parity FAILED -- refusing to mint a record" >&2
  exit 1
fi

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$HLO_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

cp "$PARITY_LOG" "$OUT_DIR/schematic-parity.txt"
printf '{\n  "exit_code": %d\n}\n' "$parity_status" > "$OUT_DIR/schematic-parity.json"

# The block-id list is derived from gen_blocks.py's own tables rather than
# duplicated here, so adding a device cannot silently escape the per-block DRC
# stage below. (`read -r` in a loop rather than `mapfile`, which macOS's system
# bash 3.2 does not have.)
BLOCKS=()
while IFS= read -r block_id; do
  BLOCKS+=("$block_id")
done < <(python3 -c "
import sys; sys.path.insert(0, '$HLO_DIR/bin')
from gen_blocks import block_ids
for block_id in block_ids():
    print(block_id)
")

# --- 1. Generate one block per schematic device ----------------------------
python3 "$HLO_DIR/bin/gen_blocks.py" "$OUT_DIR" --klt "$KLT" --pdk "$PDK_VARIANT"

# --- 2. Per-block DRC: every input block must be clean in isolation --------
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

# --- 3. Floorplan, n-well islands, taps, routing ---------------------------
python3 "$HLO_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 4. Draw the wells, taps and every wire --------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name ROUTE \
    -o route.gds --format json > draw.json )

# --- 5. Place the blocks + the well/routing cell ---------------------------
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$HLO_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/$DELIVERABLE"

# --- 6. Curated-deck DRC on the composed layout: must be CLEAN -------------
( cd "$OUT_DIR" && "$KLT" drc "$DELIVERABLE" --deck sky130 \
    --format json > drc.json ) || true

# --- 7. DRC negative control: the illegal n-well fixture, SAME deck --------
cp "$NWELL_FIXTURE" "$OUT_DIR/nwell_rules_fixture.json"
( cd "$OUT_DIR" && "$KLT" draw --params nwell_rules_fixture.json \
    --cell-name NWELL_RULES_FIXTURE -o nwell_rules_fixture.gds \
    --format json > draw.fixture.json )
( cd "$OUT_DIR" && "$KLT" drc nwell_rules_fixture.gds --deck sky130 \
    --format json > drc.fixture.json ) || true

# --- 8. Layout hygiene, on both grids --------------------------------------
( cd "$OUT_DIR" && "$KLT" precheck "$DELIVERABLE" --deck sky130 \
    --grid-um 0.001 --format json > precheck.json ) || true
( cd "$OUT_DIR" && "$KLT" precheck "$DELIVERABLE" --deck sky130 \
    --grid-um 0.005 --format json > precheck.grid5.json ) || true

# --- 9. Extract ------------------------------------------------------------
( cd "$OUT_DIR" && "$KLT" extract "$DELIVERABLE" --deck sky130 \
    --top "$TOP" -o halflsb_offset.extract.spice --format json \
    > extract.json )

# --- 10/11. References + LVS: one positive, three negative controls --------
# `top_cell_pins` is deliberately left at its default (false): every pin label
# this flow draws lives in the instanced ROUTE cell.
#
# `combine_devices` is deliberately FALSE. This sub-block instantiates no
# parallel devices for the option to fold (all eight devices are distinct in the
# schematic), so it has nothing to do here -- while KLayout's own
# Netlist.combine_devices() is known to hit an internal-consistency error on
# partial-match device groups and leave a netlist half-combined (klt's own
# `device.combine_incomplete` warning, klayout-tools#1185). Enabling an option
# with no work to do, whose failure mode is a nondeterministic verdict, would be
# trading evidence quality for nothing.
for variant in good broken-device broken-topology swapped-enable; do
  if [[ "$variant" == "good" ]]; then
    suffix=""
  else
    suffix=".$variant"
  fi
  python3 "$HLO_DIR/bin/generate-lvs-reference.py" \
    "$OUT_DIR/reference${suffix}.spice" --variant "$variant"
  cat > "$OUT_DIR/lvs${suffix}.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "${DELIVERABLE}",
    "deck": "sky130",
    "top": "${TOP}"
  },
  "reference": {
    "netlist": "reference${suffix}.spice",
    "top": "halflsb_offset"
  },
  "options": { "combine_devices": false }
}
EOF
  ( cd "$OUT_DIR" && "$KLT" lvs "lvs${suffix}.request.json" --format json \
      > "lvs${suffix}.json" ) || true
done

# --- 12. Combined human-readable report ------------------------------------
"$KLT" report "$OUT_DIR/drc.json" "$OUT_DIR/lvs.json" \
  --format github-summary > "$OUT_DIR/report.md"

# --- 13. Record summary (pass/fail verdicts, evidence-record style) --------
set +e
python3 "$HLO_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$HLO_DIR/reports/LATEST"
if [[ "$record_status" -ne 0 ]]; then
  echo "run-flow.sh: VERDICTS FAILED -- see $OUT_DIR/record.md" >&2
else
  echo "run-flow.sh: done. See $OUT_DIR/record.md"
fi
exit "$record_status"

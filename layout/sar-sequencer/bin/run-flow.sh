#!/usr/bin/env bash
# layout/sar-sequencer/bin/run-flow.sh -- place-and-route the SAR
# logic/sequencer sub-block (issue #102) and run it through DRC/LVS,
# recording a timestamped, append-only report under
# layout/sar-sequencer/reports/<record-id>/, mirroring
# layout/trivial-cell/reports/'s own convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                    # once, or after bumping requirements.txt
#   source sim/env.sh                            # exports PDK_ROOT/PDK
#   layout/sar-sequencer/bin/run-flow.sh          # ~1-2 minutes
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and an `openroad` binary on $PATH
# (`klt place-and-route` invokes it as a subprocess -- this repo's own dev
# environment provisions one via a local Docker wrapper; see
# docs/environment-setup.md).
#
# Flow (see this sub-block's own README.md "Which klt flow, and why" for the
# full rationale): `klt place-and-route` (not `klt synthesize` -- the input
# netlist is layout/sar-sequencer/netlist/sar_sequencer.v, a hand-verified
# 1:1 structural transliteration of the already-captured, already-simulated
# design/sar_sequencer.sch, not RTL) -> `klt drc` -> a small OpenROAD script
# dumping the *post-route* gate-level netlist (clock-tree/repair cells
# included) -> generate-lvs-reference.py (flattens that netlist against the
# PDK's own official CDL device models) -> `klt lvs`.
#
# LVS status (see README.md "LVS reference provenance" / the filed
# klayout-tools issue for the full writeup): this script always runs `klt
# lvs` and records whatever verdict it reports -- it does not assume
# "mismatch" is the expected outcome, so a rerun against a future klt
# release that closes the filed gap will simply record "match" without any
# script change. `set -e` is deliberately not applied to the `klt lvs`
# invocation (mismatch is exit 3, a normal documented verdict, not a script
# failure -- matching run-trivial-cell-flow.sh's own `|| true` convention
# for the same reason).
set -euo pipefail

SAR_SEQ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$SAR_SEQ_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=sar_sequencer

if [[ ! -x "$KLT" ]]; then
  echo "run-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$SAR_SEQ_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR/.klt/place-and-route"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Place-and-route -----------------------------------------------------
cp "$SAR_SEQ_DIR/netlist/sar_sequencer.v" "$OUT_DIR/sar_sequencer.v"
sed "s#../netlist/sar_sequencer.v#sar_sequencer.v#" \
  "$SAR_SEQ_DIR/requests/place-and-route.json" > "$OUT_DIR/place-and-route.json"

set +e
"$KLT" place-and-route "$OUT_DIR/place-and-route.json" --format json \
  > "$OUT_DIR/pnr.json" 2> "$OUT_DIR/pnr.stderr.log"
pnr_status=$?
set -e
if [[ $pnr_status -ne 0 ]]; then
  echo "run-flow.sh: place-and-route FAILED -- see $OUT_DIR/pnr.stderr.log" >&2
  cat "$OUT_DIR/pnr.json" >&2 || true
  echo "$RECORD_ID" > "$SAR_SEQ_DIR/reports/LATEST"
  exit 1
fi

# Flatten the final GDS/DEF up to $OUT_DIR's own top level, matching
# layout/trivial-cell/reports/<record-id>/'s flat convention -- the
# `.klt/place-and-route/` scratch subdirectory (per-stage ODB checkpoints,
# Tcl scripts, raw -metrics dumps) is a debug cache, not a deliverable, and
# is pruned at the end of this script (step 7) rather than committed.
cp "$OUT_DIR/.klt/place-and-route/${TOP}.gds" "$OUT_DIR/${TOP}.gds"
cp "$OUT_DIR/.klt/place-and-route/${TOP}.def" "$OUT_DIR/${TOP}.def"
GDS="$OUT_DIR/${TOP}.gds"

# --- 2. DRC against the sky130 deck -----------------------------------------
"$KLT" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 3. Dump the post-route gate-level netlist ------------------------------
# `klt place-and-route`'s own response has no "final netlist" field (issue
# #102's own investigation) -- read back the route-stage ODB checkpoint it
# already wrote and `write_verilog` from it directly. Invoked with `cwd` set
# to the checkpoint's own directory so the openroad Docker wrapper's `-v
# "$PWD:$PWD"` mount (see docs/environment-setup.md) covers both the input
# .odb and the output .v without needing an absolute-path remount.
cat > "$OUT_DIR/.klt/place-and-route/dump_netlist.tcl" <<EOF
read_db ${TOP}_route.odb
write_verilog ${TOP}_post_route.v
EOF
( cd "$OUT_DIR/.klt/place-and-route" && openroad -no_init -exit dump_netlist.tcl \
  > "$OUT_DIR/dump_netlist.stdout.log" 2>&1 )
cp "$OUT_DIR/.klt/place-and-route/${TOP}_post_route.v" "$OUT_DIR/${TOP}_post_route.v"

# --- 4. Generate the LVS reference from the post-route netlist --------------
python3 "$SAR_SEQ_DIR/bin/generate-lvs-reference.py" "$OUT_DIR/${TOP}_post_route.v"
REFERENCE_SRC="$SAR_SEQ_DIR/reference/sar_sequencer.lvs-reference.spice"
cp "$REFERENCE_SRC" "$OUT_DIR/sar_sequencer.lvs-reference.spice"

# --- 5. LVS: layout (extracted inline) vs. the generated reference ---------
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "file": "${TOP}.gds",
    "deck": "sky130",
    "top": "${TOP}",
    "top_cell_pins": true
  },
  "reference": {
    "netlist": "sar_sequencer.lvs-reference.spice",
    "top": "${TOP}"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

# --- 6. Record summary --------------------------------------------------
python3 "$SAR_SEQ_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" > "$OUT_DIR/record.md"

# --- 7. Prune the .klt/ scratch cache ---------------------------------------
# Per-stage ODB checkpoints, generated Tcl, and raw -metrics dumps are a
# debug cache (megabytes of binary state), not a deliverable -- the flat
# copies made in steps 1/3 above already carry everything this record needs.
rm -rf "$OUT_DIR/.klt"

echo "$RECORD_ID" > "$SAR_SEQ_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"

#!/usr/bin/env bash
# layout/bin/run-trivial-cell-flow.sh -- the sky130 klt DRC/LVS flow's gating
# proof (issue #2): generate a trivial known-good cell, run it through
# `klt gen`/`klt drc`/`klt extract`/`klt lvs` headlessly, prove the flow also
# CATCHES a deliberately injected DRC violation and two deliberately corrupted
# LVS references, and check every report into
# layout/trivial-cell/reports/<record-id>/.
#
# Usage:
#   layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
#   layout/bin/run-trivial-cell-flow.sh   # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json; `volare enable --pdk sky130 <sha>`).
#
# Exit codes: 0 all six verdicts held, 1 at least one flipped (the record is
# still written first, so the evidence trail keeps the failure).
#
# Provenance: structure ported from 2AMLogic/sky130-bandgap's
# layout/bin/run-trivial-cell-flow.sh (commit
# 1f04e8524cc2d8c2c7154773749b1b2d3be2ce64), per CLAUDE.md's "Harness
# bootstrap" instruction. One deliberate addition over that source: stages 7-8
# below, the injected-DRC-violation negative control. sky130-bandgap's flow
# proves DRC runs clean on a good cell and that LVS catches two corruptions,
# but nothing there proves the DRC deck can FAIL -- a deck that silently
# matched no rules at all would look identical. Issue #2 requires both halves
# ("a deliberately-injected DRC violation + LVS mismatch to prove the flow
# catches them"), so this repo adds the DRC negative control.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
CELL_DIR="$LAYOUT_DIR/trivial-cell"
KLT="$LAYOUT_DIR/.venv/bin/klt"
CELL=trivial_mos_array
FIXTURE=drc_violation_fixture
PDK_VARIANT=sky130A

if [[ ! -x "$KLT" ]]; then
  echo "run-trivial-cell-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-trivial-cell-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$CELL_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-trivial-cell-flow.sh: record $RECORD_ID -> $OUT_DIR"

# `klt drc` exits 3 when it finds violations and `klt lvs` exits 3 on a
# mismatch (klt reserves 3 for "ran fine, verdict was bad" and 1 for "did not
# run", so the two are distinguishable). A 3 is the EXPECTED outcome of the
# negative-control stages below, so every such invocation is `|| true`-guarded
# to survive `set -e`, and the verdict is then asserted from the JSON envelope
# by render-record.py. Asserting from JSON rather than from the exit code is
# deliberate and stricter: exit 3 says only "something was flagged", while the
# envelope says *which rule* fired, which is what the DRC negative control has
# to prove.

# --- 1. Generate the trivial known-good cell -------------------------------
"$KLT" gen mos_array --pdk "$PDK_VARIANT" --cell-name "$CELL" \
  -o "$OUT_DIR/$CELL.gds" --format json > "$OUT_DIR/gen.json"

# --- 2. DRC against the sky130 deck: must be CLEAN --------------------------
"$KLT" drc "$OUT_DIR/$CELL.gds" --deck sky130 --format json \
  > "$OUT_DIR/drc.json" || true

# --- 3. Extract a schematic-equivalent netlist ------------------------------
"$KLT" extract "$OUT_DIR/$CELL.gds" --deck sky130 --top "$CELL" \
  -o "$OUT_DIR/$CELL.extract.spice" --format json > "$OUT_DIR/extract.json"

# --- 4. LVS: known-good reference (must report "match") --------------------
cp "$CELL_DIR/reference.spice" "$OUT_DIR/reference.spice"
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

# --- 5. LVS negative control 1/2: device-parameter-only corruption ---------
cp "$CELL_DIR/reference.broken-device.spice" "$OUT_DIR/reference.broken-device.spice"
cat > "$OUT_DIR/lvs.broken-device.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.broken-device.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.broken-device.request.json" --format json \
  > "$OUT_DIR/lvs.broken-device.json" || true

# --- 6. LVS negative control 2/2: topology-only corruption (shorted net) ---
cp "$CELL_DIR/reference.broken-topology.spice" "$OUT_DIR/reference.broken-topology.spice"
cat > "$OUT_DIR/lvs.broken-topology.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.broken-topology.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.broken-topology.request.json" --format json \
  > "$OUT_DIR/lvs.broken-topology.json" || true

# --- 7. Draw the deliberately DRC-illegal fixture ---------------------------
# `klt draw` writes geometry verbatim with no rule checking, which is exactly
# what a DRC negative control needs -- see layout/bin/drc_violation_fixture.json.
cp "$LAYOUT_DIR/bin/$FIXTURE.json" "$OUT_DIR/$FIXTURE.json"
"$KLT" draw --params "$OUT_DIR/$FIXTURE.json" --cell-name "$FIXTURE" \
  -o "$OUT_DIR/$FIXTURE.gds" --format json > "$OUT_DIR/draw.json"

# --- 8. DRC negative control: the injected violation must be FLAGGED -------
"$KLT" drc "$OUT_DIR/$FIXTURE.gds" --deck sky130 --format json \
  > "$OUT_DIR/drc.injected.json" || true

# --- 9. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" "$OUT_DIR/lvs.json" \
  "$OUT_DIR/drc.injected.json" --format github-summary > "$OUT_DIR/report.md"

# --- 10. Record summary (pass/fail verdicts, evidence-record style) --------
set +e
python3 "$LAYOUT_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

# Keep a "latest" pointer so the README's quick-start doesn't need a hardcoded
# record id. A plain text file, not a symlink, so it survives a shallow
# checkout / non-symlink-preserving copy unchanged.
echo "$RECORD_ID" > "$CELL_DIR/reports/LATEST"

echo "run-trivial-cell-flow.sh: done. See $OUT_DIR/record.md"
exit "$record_status"

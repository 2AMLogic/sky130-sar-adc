# layout/bin/_flow_common.sh -- shared KLT/PDK/record-id/flow boilerplate for
# the `layout/**/run-flow*.sh` scripts (11 callers as of issue #647:
# layout/bin/run-trivial-cell-flow.sh,
# layout/cdac-array/bin/run-flow.sh,
# layout/comparator/bin/run-flow.sh,
# layout/halflsb-offset/bin/run-flow.sh,
# layout/sampling-frontend-wells/bin/run-flow.sh,
# layout/sampling-frontend/bin/run-flow.sh,
# layout/sar-adc-top/bin/run-erc.sh,
# layout/sar-adc-top/bin/run-flow.sh,
# layout/sar-sequencer/bin/run-flow.sh,
# layout/seln-inverters/bin/run-flow.sh,
# layout/top-glue/bin/run-flow.sh -- re-verify with
# `grep -rln "source .*_flow_common" layout`). Meant to be `source`d, not
# executed directly, matching the `layout/bin/_*` naming convention
# `_record_common.py` already established for a shared, non-`run-flow`-named
# helper file (#118).
#
# Each function below infers the calling script's own name from
# `${BASH_SOURCE[1]}` (the caller's frame, one level up from this file) for
# its error-message prefix, so every flow script keeps its own name in its
# error output without having to pass it explicitly.
#
# `OUT_DIR`/`mkdir -p` construction is deliberately left to each non-P&R
# caller: they write a flat `$SUBBLOCK_DIR/reports/$RECORD_ID`, and one of
# them needs no `.klt/` scratch at all. The P&R-specific
# `run_pnr_drc_lvs_flow` below constructs `OUT_DIR` itself, because the
# `mkdir -p "$OUT_DIR/.klt/place-and-route"` scratch layout it needs is
# shared by all three P&R blocks it serves (#647).

# require_klt <klt-path> -- exit 1 if <klt-path> is not an executable file.
require_klt() {
  local klt="$1"
  local prog
  prog="$(basename "${BASH_SOURCE[1]}")"
  if [[ ! -x "$klt" ]]; then
    echo "$prog: $klt not found -- run layout/bin/setup-venv.sh first" >&2
    exit 1
  fi
}

# require_pdk <klt-path> <pdk-variant> -- exit 1 if <pdk-variant> does not
# resolve via `klt pdk find`.
require_pdk() {
  local klt="$1"
  local pdk_variant="$2"
  local prog
  prog="$(basename "${BASH_SOURCE[1]}")"
  if ! "$klt" pdk find --pdk "$pdk_variant" >/dev/null; then
    echo "$prog: no resolvable $pdk_variant PDK -- see sim/pdk.json for the pin" >&2
    exit 1
  fi
}

# new_record_id <repo-root> -- echo a `<UTC-timestamp>-<short-sha>` record id.
new_record_id() {
  local repo_root="$1"
  local ts_utc short_sha
  ts_utc="$(date -u +%Y%m%d-%H%M%S)"
  short_sha="$(git -C "$repo_root" rev-parse --short HEAD)"
  echo "${ts_utc}-${short_sha}"
}

# run_pnr_drc_lvs_flow <block-dir> <repo-root> <klt-path> <pdk-variant> <top>
#
# The place-and-route -> DRC -> post-route netlist dump -> LVS-reference ->
# extract -> LVS -> record.md -> .klt-prune pipeline shared verbatim by the
# three P&R flow scripts (sar-sequencer, seln-inverters, top-glue; #647).
# Call it after require_klt/require_pdk and the openroad-on-$PATH check.
#
# Optional hook points for block-specific steps, each set to the NAME of a
# zero-argument function defined in the caller (empty/unset = skip):
#   FLOW_PRE_ROUTE_HOOK   after the record directory is created, before P&R
#                         (top-glue's captured pre-route schematic-parity run)
#   FLOW_POST_ROUTE_HOOK  after the post-route netlist is dumped and flattened
#                         into the record, before the LVS reference is
#                         generated from it (top-glue's post-route parity run)
# Hooks see the caller's own globals plus the flow's RECORD_ID/OUT_DIR/GDS.
# A hook failure aborts the script under the caller's `set -e` before the
# place-and-route failure handler runs, so no `reports/LATEST` pointer is
# written for a hook failure -- matching the pre-#647 inline behavior, where
# a parity failure never minted a usable record pointer.
run_pnr_drc_lvs_flow() {
  local block_dir="$1" repo_root="$2" klt="$3" pdk_variant="$4" top="$5"
  local prog pnr_status
  prog="$(basename "${BASH_SOURCE[1]}")"

  RECORD_ID="$(new_record_id "$repo_root")"
  OUT_DIR="$block_dir/reports/$RECORD_ID"
  mkdir -p "$OUT_DIR/.klt/place-and-route"
  echo "$prog: record $RECORD_ID -> $OUT_DIR"

  if [[ -n "${FLOW_PRE_ROUTE_HOOK:-}" ]]; then "$FLOW_PRE_ROUTE_HOOK"; fi

  # --- 1. Place-and-route -----------------------------------------------------
  cp "$block_dir/netlist/${top}.v" "$OUT_DIR/${top}.v"
  sed "s#../netlist/${top}.v#${top}.v#" \
    "$block_dir/requests/place-and-route.json" > "$OUT_DIR/place-and-route.json"

  set +e
  "$klt" place-and-route "$OUT_DIR/place-and-route.json" --format json \
    > "$OUT_DIR/pnr.json" 2> "$OUT_DIR/pnr.stderr.log"
  pnr_status=$?
  set -e
  if [[ $pnr_status -ne 0 ]]; then
    echo "$prog: place-and-route FAILED -- see $OUT_DIR/pnr.stderr.log" >&2
    cat "$OUT_DIR/pnr.json" >&2 || true
    echo "$RECORD_ID" > "$block_dir/reports/LATEST"
    exit 1
  fi

  # Flatten the final GDS/DEF up to $OUT_DIR's own top level, matching
  # layout/trivial-cell/reports/<record-id>/'s flat convention -- the
  # `.klt/place-and-route/` scratch subdirectory (per-stage ODB checkpoints,
  # Tcl scripts, raw -metrics dumps) is a debug cache, not a deliverable, and
  # is pruned at the end of this function (step 8) rather than committed.
  cp "$OUT_DIR/.klt/place-and-route/${top}.gds" "$OUT_DIR/${top}.gds"
  cp "$OUT_DIR/.klt/place-and-route/${top}.def" "$OUT_DIR/${top}.def"
  GDS="$OUT_DIR/${top}.gds"

  # --- 2. DRC against the sky130 deck -----------------------------------------
  "$klt" drc "$GDS" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

  # --- 3. Dump the post-route gate-level netlist ------------------------------
  # `klt place-and-route`'s own response has no "final netlist" field (issue
  # #102's own investigation) -- read back the route-stage ODB checkpoint it
  # already wrote and `write_verilog` from it directly. Invoked with `cwd` set
  # to the checkpoint's own directory so the openroad Docker wrapper's `-v
  # "$PWD:$PWD"` mount (see docs/environment-setup.md) covers both the input
  # .odb and the output .v without needing an absolute-path remount.
  cat > "$OUT_DIR/.klt/place-and-route/dump_netlist.tcl" <<EOF
read_db ${top}_route.odb
write_verilog ${top}_post_route.v
EOF
  ( cd "$OUT_DIR/.klt/place-and-route" && openroad -no_init -exit dump_netlist.tcl \
    > "$OUT_DIR/dump_netlist.stdout.log" 2>&1 )
  cp "$OUT_DIR/.klt/place-and-route/${top}_post_route.v" "$OUT_DIR/${top}_post_route.v"

  if [[ -n "${FLOW_POST_ROUTE_HOOK:-}" ]]; then "$FLOW_POST_ROUTE_HOOK"; fi

  # --- 4. Generate the LVS reference from the post-route netlist --------------
  python3 "$block_dir/bin/generate-lvs-reference.py" "$OUT_DIR/${top}_post_route.v"
  cp "$block_dir/reference/${top}.lvs-reference.spice" \
    "$OUT_DIR/${top}.lvs-reference.spice"

  # --- 5. Extract, deriving the declared pin set from the routed DEF ---------
  # `--def-pins` (klt 0.4.0, klayout-tools#1390/#1397) replaces the earlier
  # inline `layout.top_cell_pins: true` LVS request (klt 0.2.0/0.3.0):
  # `--top-cell-pins`'s "only labels drawn directly in the top cell" heuristic
  # cannot tell a genuine top-level design port from an internal DEF NETS
  # connection point once a DEF->GDS merge flattens the whole design into the
  # top cell -- see README.md "LVS reference provenance" for the full
  # investigation and 2AMLogic/klayout-tools#1385, the tool gap filed against
  # the earlier (0.3.0-era) attempt. `--def-pins "${top}.def"` instead derives
  # the declared pin set directly from the routed DEF's own PINS section, so
  # extraction runs as an explicit pre-step here (its own committed
  # extract.spice/extract.json) rather than inline inside the `klt lvs`
  # request.
  "$klt" extract "$GDS" --deck sky130 --top "$top" --def-pins "$OUT_DIR/${top}.def" \
    -o "$OUT_DIR/${top}.extract.spice" --format json > "$OUT_DIR/extract.json" || true

  # --- 6. LVS: pre-extracted layout netlist vs. the generated reference -------
  cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": {
    "netlist": "${top}.extract.spice",
    "top": "${top}"
  },
  "reference": {
    "netlist": "${top}.lvs-reference.spice",
    "top": "${top}"
  },
  "options": {
    "combine_devices": true
  }
}
EOF
  "$klt" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

  # --- 7. Record summary --------------------------------------------------
  python3 "$block_dir/bin/render-record.py" \
    --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$repo_root" \
    --klt "$klt" --pdk-variant "$pdk_variant" > "$OUT_DIR/record.md"

  # --- 8. Prune the .klt/ scratch cache ---------------------------------------
  # Per-stage ODB checkpoints, generated Tcl, and raw -metrics dumps are a
  # debug cache (megabytes of binary state), not a deliverable -- the flat
  # copies made in steps 1/3 above already carry everything this record needs.
  rm -rf "$OUT_DIR/.klt"

  echo "$RECORD_ID" > "$block_dir/reports/LATEST"
  echo "$prog: done. See $OUT_DIR/record.md"
}

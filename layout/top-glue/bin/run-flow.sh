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
# Steps 1-7 are _flow_common.sh's run_pnr_drc_lvs_flow, shared with the
# sar-sequencer and seln-inverters flow scripts (#647). Step 0 is this
# block's own and has three runs, in this order:
#   0a. the bare gate above, BEFORE the record directory is created -- a
#       drifted netlist must not mint a record at all;
#   0b. a captured run opening the record's schematic-parity.txt, via the
#       shared flow's FLOW_PRE_ROUTE_HOOK;
#   0c. a post-route run against the routed netlist, appending to the same
#       file via FLOW_POST_ROUTE_HOOK -- proving the router did not add,
#       drop or rename an instance on the way to the GDS the LVS reference
#       is generated from.
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
# klt resolves the PDK from $PDK; unset, it can pick a sibling (gf180mcu) install.
export PDK=sky130A
TOP=top_glue

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

# --- 0a. Schematic parity: the independent anchor (issue #387) ---------------
# Deliberately BEFORE the record directory is created: a netlist that has
# drifted from the schematic must not mint a record at all, so no future
# reader can cite a DRC/LVS verdict over geometry built from the wrong
# topology.
python3 "$BLOCK_DIR/bin/check-schematic-parity.py"

# --- 0b/0c. The gate's two in-record runs, as flow hooks --------------------
# (the hooks see the shared flow's OUT_DIR once the record exists)
flow_parity_pre_route() {
  python3 "$BLOCK_DIR/bin/check-schematic-parity.py" \
    > "$OUT_DIR/schematic-parity.txt" 2>&1
}
flow_parity_post_route() {
  python3 "$BLOCK_DIR/bin/check-schematic-parity.py" \
    --netlist "$OUT_DIR/${TOP}_post_route.v" \
    >> "$OUT_DIR/schematic-parity.txt" 2>&1
}
FLOW_PRE_ROUTE_HOOK=flow_parity_pre_route
FLOW_POST_ROUTE_HOOK=flow_parity_post_route

run_pnr_drc_lvs_flow "$BLOCK_DIR" "$REPO_ROOT" "$KLT" "$PDK_VARIANT" "$TOP"

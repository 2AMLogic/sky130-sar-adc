#!/usr/bin/env bash
# layout/seln-inverters/bin/run-flow.sh -- place-and-route the SELn<i> =
# NOT(DOUT<i>) inverter bank (issue #103's own new top-level glue logic --
# see netlist/seln_inverters.v's header for why this belongs to the
# integration issue rather than any sub-block) and run it through DRC/LVS,
# recording a timestamped, append-only report under
# layout/seln-inverters/reports/<record-id>/, mirroring
# layout/sar-sequencer/reports/'s own convention (see layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh                     # once, or after bumping requirements.txt
#   source sim/env.sh                             # exports PDK_ROOT/PDK
#   layout/seln-inverters/bin/run-flow.sh          # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and an `openroad` binary on $PATH
# (`klt place-and-route` invokes it as a subprocess -- see
# docs/environment-setup.md).
#
# Flow (identical shape to layout/sar-sequencer/bin/run-flow.sh, minus its
# clock-tree-specific steps -- this design is purely combinational, so a
# nominal clock_port/clock_period_ns is declared only to satisfy
# `klt place-and-route`'s own request schema, per requests/place-and-route.json's
# comment): `klt place-and-route` -> `klt drc` -> post-route netlist dump ->
# generate-lvs-reference.py -> `klt extract --def-pins` -> `klt lvs`. The
# pipeline itself is _flow_common.sh's run_pnr_drc_lvs_flow, shared with the
# sar-sequencer and top-glue flow scripts (#647); this script only
# contributes the block-specific rationale above and no hooks.
set -euo pipefail

BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=seln_inverters

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

run_pnr_drc_lvs_flow "$BLOCK_DIR" "$REPO_ROOT" "$KLT" "$PDK_VARIANT" "$TOP"

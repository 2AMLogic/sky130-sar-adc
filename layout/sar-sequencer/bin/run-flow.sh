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
# PDK's own official CDL device models) -> `klt extract --def-pins` -> `klt
# lvs`. The pipeline itself is _flow_common.sh's run_pnr_drc_lvs_flow,
# shared with the seln-inverters and top-glue flow scripts (#647); this
# script only contributes the block-specific rationale above and no hooks.
#
# LVS status (see README.md "LVS reference provenance" / the filed
# klayout-tools issue for the full writeup): the shared flow always runs
# `klt lvs` and records whatever verdict it reports -- it does not assume
# any particular outcome, so a rerun against a future klt release simply
# records whatever verdict that release reaches without any script change.
# `set -e` is deliberately not applied to the `klt extract`/`klt lvs`
# invocations (a non-clean/mismatch verdict is a normal documented exit
# code, not a script failure -- matching run-trivial-cell-flow.sh's own
# `|| true` convention for the same reason).
set -euo pipefail

BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
# klt resolves the PDK from $PDK; unset, it can pick a sibling (gf180mcu) install.
export PDK=sky130A
TOP=sar_sequencer

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

if ! command -v openroad >/dev/null 2>&1; then
  echo "run-flow.sh: no 'openroad' binary on \$PATH -- see docs/environment-setup.md" >&2
  exit 1
fi

run_pnr_drc_lvs_flow "$BLOCK_DIR" "$REPO_ROOT" "$KLT" "$PDK_VARIANT" "$TOP"

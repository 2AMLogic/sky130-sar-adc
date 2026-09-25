#!/usr/bin/env bash
# layout/bin/setup-erc-venv.sh -- creates/refreshes layout/.venv-erc with the
# `klt` build pinned in layout/erc-requirements.txt, used by exactly one flow:
# layout/sar-adc-top/bin/run-erc.sh (T1 item 11, issue #344).
#
#   layout/bin/setup-erc-venv.sh          # create if missing, otherwise no-op
#   layout/bin/setup-erc-venv.sh --force  # reinstall even if it exists
#
# This is deliberately a SECOND venv beside layout/.venv (layout/bin/
# setup-venv.sh, klayout-tools==0.5.0), not a replacement for it -- see
# layout/erc-requirements.txt's own header for why the ERC run is pinned
# separately from the DRC/LVS flow, and why that separation is safe.
#
# Structure ported verbatim from layout/bin/setup-venv.sh, including its
# `--force-reinstall` discipline; only the venv path, the requirements file
# and the absent `klt pdk find` check differ. `klt erc` resolves no PDK
# install (it reads a GDS and a JSON spec, and `--deck sky130` is the curated
# in-package deck registry, not an installed PDK), so there is nothing for
# this script to probe.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$LAYOUT_DIR/.venv-erc"

if [[ -x "$VENV/bin/klt" && "${1:-}" != "--force" ]]; then
  echo "setup-erc-venv.sh: $VENV already has klt installed (pass --force to reinstall)"
  "$VENV/bin/klt" --version
  exit 0
fi

echo "setup-erc-venv.sh: creating $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet --force-reinstall --no-deps \
  -r "$LAYOUT_DIR/erc-requirements.txt"
"$VENV/bin/pip" install --quiet -r "$LAYOUT_DIR/erc-requirements.txt"

echo "setup-erc-venv.sh: installed"
"$VENV/bin/klt" --version

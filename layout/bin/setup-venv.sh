#!/usr/bin/env bash
# Source or run me: creates/refreshes layout/.venv with the pinned `klt`
# build from layout/requirements.txt.
#
#   layout/bin/setup-venv.sh          # create if missing, otherwise no-op
#   layout/bin/setup-venv.sh --force  # reinstall even if .venv/bin/klt exists
#
# Provenance: ported from 2AMLogic/sky130-bandgap's layout/bin/setup-venv.sh
# (commit 1f04e8524cc2d8c2c7154773749b1b2d3be2ce64), per CLAUDE.md's
# "Harness bootstrap" instruction -- unchanged except for this header.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$LAYOUT_DIR/.venv"

if [[ -x "$VENV/bin/klt" && "${1:-}" != "--force" ]]; then
  echo "setup-venv.sh: $VENV already has klt installed (pass --force to reinstall)"
  "$VENV/bin/klt" --version
  exit 0
fi

echo "setup-venv.sh: creating $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
# `--force-reinstall` matters even for a plain version pin: without it, a
# `pip install -r` that finds the pinned version already satisfied (e.g. a
# stale editable/dev install of the same version number) can silently leave
# an old build in place. Cheap insurance, same discipline sky130-bandgap's
# script applies for its git-commit pin.
"$VENV/bin/pip" install --quiet --force-reinstall --no-deps \
  -r "$LAYOUT_DIR/requirements.txt"
"$VENV/bin/pip" install --quiet -r "$LAYOUT_DIR/requirements.txt"

echo "setup-venv.sh: installed"
"$VENV/bin/klt" --version
"$VENV/bin/klt" pdk find --pdk sky130A || {
  echo "setup-venv.sh: WARNING: no resolvable sky130A PDK install found." >&2
  echo "  See sim/pdk.json for this repo's pinned install command." >&2
}

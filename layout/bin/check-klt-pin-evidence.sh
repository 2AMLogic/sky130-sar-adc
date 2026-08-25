#!/usr/bin/env bash
# layout/bin/check-klt-pin-evidence.sh -- cheap, headless cross-check that the
# `klt` pin in layout/requirements.txt matches the pin the latest six-verdict
# trivial-cell proof (layout/bin/run-trivial-cell-flow.sh) was actually run
# against, and that that proof's overall verdict is PASS (issue #110).
#
# Why (#110): the DRC/LVS trivial-cell proof only runs in CI's PDK-gated
# `pdk-smoke` job (schedule / workflow_dispatch / opt-in `run-pdk-smoke` PR
# label) -- correct for cost reasons, but it leaves a blind spot: a PR that
# bumps the `klt` pin in layout/requirements.txt is exactly the PR where the
# proof most needs to re-run, and exactly the PR where nobody remembers to
# add the label. PR #108 bumped the pin (0.2.0 -> 0.3.0) with no
# `run-pdk-smoke` label; `pdk-smoke` never ran; the pin bump merged to `main`
# with the gating proof silently broken (LVS verdict flipped, per klt 0.3.0's
# dummy-device-suppression fix changing the trivial cell's device count from
# 8 to 4) until #104 restored it a day later. This check catches exactly that
# regression, headlessly, on every PR/push -- no PDK fetch, no `klt` install,
# no layout/.venv required, so it runs in the `checks` job (part of
# `npm run check:ci`) rather than needing `pdk-smoke`'s PDK-gated cost.
#
# This is Option 2 of #110's three proposed fixes -- the always-on, PDK-free
# gate. It is deliberately narrower than Option 1 (path-triggering
# `pdk-smoke` itself): it does not *produce* fresh evidence, it only refuses
# to let a pin move without evidence that already matches. A pin bump still
# requires a human/agent to run layout/bin/run-trivial-cell-flow.sh (locally,
# or via the `run-pdk-smoke` PR label) and commit the fresh report -- exactly
# as #104's fix did for the #108 regression.
#
# What it checks:
#   1. layout/requirements.txt pins `klayout-tools==X.Y.Z`.
#   2. layout/trivial-cell/reports/LATEST names a report directory.
#   3. That report's record.md stamps `` `klt` version: `klt X.Y.Z` `` --
#      and X.Y.Z must equal the pin from (1).
#   4. That record.md's `## Overall verdict:` line reads `PASS`.
#
# A comment-only or non-version edit to layout/requirements.txt (i.e. the
# `klayout-tools==X.Y.Z` line itself unchanged) trivially still matches the
# latest record, so it does not spuriously fail this check.
#
# Usage:
#   layout/bin/check-klt-pin-evidence.sh [ROOT]
#     ROOT  Repository root. Defaults to `git rev-parse --show-toplevel`,
#           then the script's own repo root.
#
# Exit codes: 0 = pin matches the latest report's stamped `klt` version AND
# that report's overall verdict is PASS; 1 = mismatch, missing evidence, or
# non-PASS verdict (actionable message on stderr).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ROOT="$1"
else
  if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    :
  else
    ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
  fi
fi

REQUIREMENTS="$ROOT/layout/requirements.txt"
REPORTS_DIR="$ROOT/layout/trivial-cell/reports"
LATEST_FILE="$REPORTS_DIR/LATEST"

fail() {
  echo "check-klt-pin-evidence.sh: $1" >&2
  echo "" >&2
  echo "Fix: re-run ./layout/bin/setup-venv.sh && ./layout/bin/run-trivial-cell-flow.sh" >&2
  echo "     and commit the fresh layout/trivial-cell/reports/<record-id>/ directory" >&2
  echo "     (this needs a resolvable sky130A PDK -- either locally, or by adding the" >&2
  echo "     'run-pdk-smoke' label to your PR so CI's pdk-smoke job produces it)." >&2
  exit 1
}

[[ -f "$REQUIREMENTS" ]] || fail "$REQUIREMENTS not found"

PINNED_VERSION="$(grep -E '^klayout-tools==' "$REQUIREMENTS" | head -1 | sed -E 's/^klayout-tools==([0-9][0-9A-Za-z.+-]*)[[:space:]]*$/\1/')"
if [[ -z "$PINNED_VERSION" ]]; then
  fail "no 'klayout-tools==X.Y.Z' pin found in $REQUIREMENTS"
fi

[[ -f "$LATEST_FILE" ]] || fail "$LATEST_FILE not found -- no trivial-cell proof evidence recorded"

RECORD_ID="$(tr -d '[:space:]' < "$LATEST_FILE")"
if [[ -z "$RECORD_ID" ]]; then
  fail "$LATEST_FILE is empty"
fi

RECORD_MD="$REPORTS_DIR/$RECORD_ID/record.md"
[[ -f "$RECORD_MD" ]] || fail "$RECORD_MD not found (LATEST points at record '$RECORD_ID')"

# Deliberately single-quoted literal (no expansion wanted).
# shellcheck disable=SC2016
KLT_VERSION_PATTERN='`klt` version: `klt [0-9][0-9A-Za-z.+-]*`'
RECORD_VERSION="$(grep -oE "$KLT_VERSION_PATTERN" "$RECORD_MD" | head -1 | sed -E 's/.*klt ([0-9][0-9A-Za-z.+-]*)`/\1/')"
if [[ -z "$RECORD_VERSION" ]]; then
  fail "$RECORD_MD has no '\`klt\` version: \`klt X.Y.Z\`' provenance line"
fi

if [[ "$PINNED_VERSION" != "$RECORD_VERSION" ]]; then
  fail "layout/requirements.txt pins klt $PINNED_VERSION but the latest trivial-cell report ($RECORD_ID) was run against klt $RECORD_VERSION -- the pin moved without fresh evidence"
fi

VERDICT="$(grep -E '^## Overall verdict:' "$RECORD_MD" | head -1 | sed -E 's/^## Overall verdict:[[:space:]]*//')"
if [[ -z "$VERDICT" ]]; then
  fail "$RECORD_MD has no '## Overall verdict:' line"
fi

if [[ "$VERDICT" != "PASS" ]]; then
  fail "the latest trivial-cell report ($RECORD_ID, klt $RECORD_VERSION) has overall verdict '$VERDICT', not PASS"
fi

echo "check-klt-pin-evidence.sh: OK -- klt $PINNED_VERSION matches latest trivial-cell report ($RECORD_ID), overall verdict PASS"

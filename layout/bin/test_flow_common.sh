#!/usr/bin/env bash
# layout/bin/test_flow_common.sh -- self-test for layout/bin/_flow_common.sh's
# shared flow helpers (issue #915).
#
#   layout/bin/test_flow_common.sh
#
# Needs no PDK, no `klt` and no layout/.venv: it builds a throwaway block tree
# with stub `klt`/render-record.py executables, so it runs in the always-on
# headless `checks` CI job rather than only in a PDK-gated layout flow.
#
# What it is for. The per-block flow equivalence of the #915 factoring was
# demonstrated by re-running all eight `layout/*/bin/run-flow.sh` flows and
# diffing the records (see that issue's PR), but a PASSING flow run cannot
# exercise two things the helpers are responsible for:
#
#   1. the FAILED-verdict path of `finish_record` -- the stderr line and the
#      non-zero exit a flow takes when render-record.py rejects a verdict.
#      Before #915 two of the four callers carrying that tail printed `done.`
#      and exited non-zero, which read as a pass; the uniform branch now lives
#      in one place, so it is checked here once for all of them.
#   2. `flow_caller_name`'s whole reason to exist -- that an error raised
#      through a nested helper (`flow_init` -> `require_klt`) still names the
#      `run-flow.sh` the operator invoked, not `_flow_common.sh`.
#
# Each assertion that has a meaningful opposite is run against both arms (a
# failing AND a passing render-record.py; an absent AND a present `klt`),
# matching this repo's negative-control discipline for the flows themselves.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
PROG="$(basename "${BASH_SOURCE[0]}")"

FAILURES=0
CHECKS=0

ok() {
  CHECKS=$((CHECKS + 1))
  echo "$PROG: ok -- $1"
}

fail() {
  CHECKS=$((CHECKS + 1))
  FAILURES=$((FAILURES + 1))
  echo "$PROG: FAIL -- $1" >&2
  echo "    expected: $2" >&2
  echo "    actual:   $3" >&2
}

expect_eq() {
  local what="$1" want="$2" got="$3"
  if [[ "$want" == "$got" ]]; then ok "$what"; else fail "$what" "$want" "$got"; fi
}

expect_contains() {
  local what="$1" needle="$2" haystack="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    ok "$what"
  else
    fail "$what" "output containing '$needle'" "$haystack"
  fi
}

# --- A throwaway block tree ---------------------------------------------------
# Mirrors the real layout/<block>/ shape closely enough for the helpers:
#   $T/layout/bin/_flow_common.sh   the file under test (copied, not sourced
#                                   in place, so $LAYOUT_DIR resolution is
#                                   exercised against the fake tree)
#   $T/layout/.venv/bin/klt         stub: records its argv, answers `pdk find`
#   $T/layout/testblock/bin/        stub render-record.py + the test callers
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

mkdir -p "$T/layout/bin" "$T/layout/.venv/bin" \
         "$T/layout/testblock/bin" "$T/layout/testblock/reports"
cp "$LAYOUT_DIR/bin/_flow_common.sh" "$T/layout/bin/_flow_common.sh"
# `new_record_id` shells out to `git -C <repo-root> rev-parse --short HEAD`,
# so the fake tree needs to be a repo with one commit.
git -C "$T" init -q
git -C "$T" -c user.email=t@t -c user.name=t commit -q --allow-empty -m t

BLOCK="$T/layout/testblock"

cat > "$T/layout/.venv/bin/klt" <<'EOF'
#!/usr/bin/env bash
# Stub klt. `pdk find` succeeds; `drc` emits a recognisable envelope; `report`
# writes nothing of consequence. Every call is appended to $KLT_CALLS.
[[ -n "${KLT_CALLS:-}" ]] && printf '%s\n' "$*" >> "$KLT_CALLS"
case "$1" in
  "pdk") exit 0 ;;
  "drc") echo "{\"stub_drc\": \"$2\"}" ;;
  *) : ;;
esac
EOF
chmod +x "$T/layout/.venv/bin/klt"

# render-record.py's exit code is what finish_record propagates. $RR_EXIT
# selects the arm.
cat > "$BLOCK/bin/render-record.py" <<'EOF'
import os, sys
print("stub record.md")
sys.exit(int(os.environ.get("RR_EXIT", "0")))
EOF

# --- The test callers ---------------------------------------------------------
# Separate scripts, not functions, because flow_caller_name's contract is
# about the bash call stack's FILE names: the whole point is that these are
# named run-flow.sh, so a correct error message says "run-flow.sh:".
cat > "$BLOCK/bin/run-flow.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
source "$LAYOUT_DIR/bin/_flow_common.sh"
flow_init "$BLOCK_DIR" "${KLT_OVERRIDE:-}"
echo "KLT=$KLT"
echo "PDK=$PDK"
echo "PDK_VARIANT=$PDK_VARIANT"
echo "REPO_ROOT=$REPO_ROOT"
echo "LAYOUT_DIR=$LAYOUT_DIR"
flow_begin_record "$BLOCK_DIR"
echo "RECORD_ID=$RECORD_ID"
echo "OUT_DIR=$OUT_DIR"
BLOCKS=(alpha beta)
drc_blocks_fanout "$OUT_DIR" "${BLOCKS[@]}"
: > "$OUT_DIR/drc.json"
: > "$OUT_DIR/lvs.json"
finish_record "$BLOCK_DIR" "$OUT_DIR" "$RECORD_ID"
echo "UNREACHABLE: finish_record returned instead of exiting"
EOF
chmod +x "$BLOCK/bin/run-flow.sh"

# A second caller that only calls require_klt DIRECTLY, the shape the three
# flow scripts #915 left unconverted (run-trivial-cell-flow.sh, run-erc.sh,
# probe-hierarchical-lvs.sh) still use.
cat > "$BLOCK/bin/run-direct.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
BLOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$BLOCK_DIR/.." && pwd)"
source "$LAYOUT_DIR/bin/_flow_common.sh"
require_klt "${KLT_PATH:-$LAYOUT_DIR/.venv/bin/klt}"
echo "require_klt accepted"
EOF
chmod +x "$BLOCK/bin/run-direct.sh"

echo "$PROG: block tree at $T"

# --- 1. flow_init: defaults, and the gates it runs ---------------------------
out="$(cd / && KLT_CALLS="$T/calls.txt" "$BLOCK/bin/run-flow.sh" 2>"$T/err.txt")" || true
expect_contains "flow_init defaults KLT to the pinned .venv/bin/klt" \
  "KLT=$T/layout/.venv/bin/klt" "$out"
expect_contains "flow_init derives LAYOUT_DIR from the block dir" \
  "LAYOUT_DIR=$T/layout" "$out"
expect_contains "flow_init derives REPO_ROOT one level above LAYOUT_DIR" \
  "REPO_ROOT=$T" "$out"
expect_contains "flow_init sets PDK_VARIANT=sky130A" "PDK_VARIANT=sky130A" "$out"
expect_contains "flow_init exports PDK=sky130A" "PDK=sky130A" "$out"

# The one thing a stray environment must NOT be able to do: retarget the flow.
out_stray="$(cd / && PDK=gf180mcuD KLT="/nonexistent/ambient/klt" \
  "$BLOCK/bin/run-flow.sh" 2>"$T/err-stray.txt")" || true
expect_contains "flow_init overrides a stray \$PDK from a sibling install" \
  "PDK=sky130A" "$out_stray"
expect_contains "flow_init ignores an ambient \$KLT (override is an argument)" \
  "KLT=$T/layout/.venv/bin/klt" "$out_stray"

# ...while an explicitly passed override IS honoured (sar-adc-top's
# $SAR_ADC_TOP_KLT path).
cp "$T/layout/.venv/bin/klt" "$T/other-klt"
out_override="$(cd / && KLT_OVERRIDE="$T/other-klt" "$BLOCK/bin/run-flow.sh" \
  2>"$T/err-override.txt")" || true
expect_contains "flow_init honours an explicit klt override argument" \
  "KLT=$T/other-klt" "$out_override"

# --- 2. flow_caller_name: error prefixes name the caller, not this file ------
# Through the nested path (flow_init -> require_klt), which is the regression
# flow_caller_name exists to prevent.
set +e
err_nested="$(cd / && KLT_OVERRIDE="/nonexistent/klt" "$BLOCK/bin/run-flow.sh" 2>&1 >/dev/null)"
rc_nested=$?
set -e
expect_eq "a missing klt reached through flow_init exits 1" "1" "$rc_nested"
expect_contains "nested require_klt failure names run-flow.sh" \
  "run-flow.sh: /nonexistent/klt not found" "$err_nested"
if [[ "$err_nested" == *"_flow_common.sh:"* ]]; then
  fail "nested require_klt failure must not name _flow_common.sh" \
    "no '_flow_common.sh:' prefix" "$err_nested"
else
  ok "nested require_klt failure does not name _flow_common.sh"
fi

# And through the direct path the unconverted callers still use.
set +e
err_direct="$(cd / && KLT_PATH="/nonexistent/klt" "$BLOCK/bin/run-direct.sh" 2>&1 >/dev/null)"
rc_direct=$?
set -e
expect_eq "a missing klt reached directly exits 1" "1" "$rc_direct"
expect_contains "direct require_klt failure names run-direct.sh" \
  "run-direct.sh: /nonexistent/klt not found" "$err_direct"

# Positive control for the same gate: a present klt is accepted.
out_direct="$(cd / && "$BLOCK/bin/run-direct.sh")"
expect_contains "a present klt is accepted by require_klt" \
  "require_klt accepted" "$out_direct"

# --- 3. flow_begin_record ----------------------------------------------------
record_id="$(printf '%s\n' "$out" | sed -n 's/^RECORD_ID=//p')"
out_dir="$(printf '%s\n' "$out" | sed -n 's/^OUT_DIR=//p')"
if [[ "$record_id" =~ ^[0-9]{8}-[0-9]{6}-[0-9a-f]+$ ]]; then
  ok "flow_begin_record mints a <UTC-timestamp>-<short-sha> record id"
else
  fail "flow_begin_record mints a <UTC-timestamp>-<short-sha> record id" \
    "YYYYmmdd-HHMMSS-<sha>" "$record_id"
fi
expect_eq "flow_begin_record puts OUT_DIR under the block's reports/" \
  "$BLOCK/reports/$record_id" "$out_dir"
if [[ -d "$out_dir" ]]; then
  ok "flow_begin_record creates OUT_DIR"
else
  fail "flow_begin_record creates OUT_DIR" "a directory at $out_dir" "absent"
fi
expect_contains "flow_begin_record announces the record, prefixed by the caller" \
  "run-flow.sh: record $record_id -> $out_dir" "$out"

# --- 4. drc_blocks_fanout ----------------------------------------------------
fanout="$(cat "$out_dir/drc.blocks.json")"
# The `,` sits on its own line because each `klt drc --format json` stdout
# ends with a newline and the separator is prepended to the NEXT entry. That
# is the shape every committed layout/*/reports/*/drc.blocks.json already has
# (e.g. the separator lines in layout/comparator/'s own records), so it is
# pinned here rather than tidied: this test exists to hold the hoisted helper
# to the inline block's byte-for-byte output, not to improve on it.
expect_eq "drc_blocks_fanout writes one envelope keyed by block id" \
  '{
  "alpha": {"stub_drc": "'"$out_dir"'/alpha.gds"}
,
  "beta": {"stub_drc": "'"$out_dir"'/beta.gds"}
}' "$fanout"
if python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$out_dir/drc.blocks.json"; then
  ok "drc_blocks_fanout's envelope is valid JSON"
else
  fail "drc_blocks_fanout's envelope is valid JSON" "parseable" "parse error"
fi
expect_contains "drc_blocks_fanout invokes the deck the flows record against" \
  "drc $out_dir/alpha.gds --deck sky130 --format json" "$(cat "$T/calls.txt")"

# --- 5. finish_record: both arms --------------------------------------------
# PASS arm: "done.", exit 0, LATEST updated.
set +e
pass_out="$(cd / && RR_EXIT=0 "$BLOCK/bin/run-flow.sh" 2>"$T/pass-err.txt")"
pass_rc=$?
set -e
pass_record="$(printf '%s\n' "$pass_out" | sed -n 's/^RECORD_ID=//p')"
expect_eq "finish_record exits 0 when render-record.py accepts the verdicts" \
  "0" "$pass_rc"
expect_contains "finish_record reports done. on the passing arm" \
  "run-flow.sh: done. See $BLOCK/reports/$pass_record/record.md" "$pass_out"
expect_eq "finish_record points reports/LATEST at the new record" \
  "$pass_record" "$(cat "$BLOCK/reports/LATEST")"
if [[ -s "$BLOCK/reports/$pass_record/record.md" ]]; then
  ok "finish_record writes the record.md render-record.py produced"
else
  fail "finish_record writes the record.md render-record.py produced" \
    "non-empty record.md" "missing or empty"
fi
if [[ "$(cat "$T/pass-err.txt")" == *"VERDICTS FAILED"* ]]; then
  fail "finish_record is silent on stderr on the passing arm" \
    "no VERDICTS FAILED line" "$(cat "$T/pass-err.txt")"
else
  ok "finish_record is silent on stderr on the passing arm"
fi

# FAIL arm: the stderr line, a non-zero exit, and the record trail KEPT --
# the pointer must still move, because the record it just wrote is the
# evidence of why the verdict failed.
set +e
fail_out="$(cd / && RR_EXIT=3 "$BLOCK/bin/run-flow.sh" 2>"$T/fail-err.txt")"
fail_rc=$?
set -e
fail_record="$(printf '%s\n' "$fail_out" | sed -n 's/^RECORD_ID=//p')"
expect_eq "finish_record propagates render-record.py's own non-zero status" \
  "3" "$fail_rc"
expect_contains "finish_record reports VERDICTS FAILED on stderr" \
  "run-flow.sh: VERDICTS FAILED -- see $BLOCK/reports/$fail_record/record.md" \
  "$(cat "$T/fail-err.txt")"
if [[ "$fail_out" == *"done."* ]]; then
  fail "finish_record must not report done. on the failing arm" \
    "no 'done.' on stdout" "$fail_out"
else
  ok "finish_record does not report done. on the failing arm"
fi
expect_eq "finish_record still moves reports/LATEST on a failed verdict" \
  "$fail_record" "$(cat "$BLOCK/reports/LATEST")"
if [[ "$fail_out" == *"UNREACHABLE"* ]]; then
  fail "finish_record is terminal (exits, does not return)" \
    "no statement after finish_record runs" "$fail_out"
else
  ok "finish_record is terminal (exits, does not return)"
fi

# --- Verdict ------------------------------------------------------------------
echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "$PROG: PASS -- $CHECKS checks"
else
  echo "$PROG: FAIL -- $FAILURES of $CHECKS checks failed" >&2
fi
exit $(( FAILURES > 0 ? 1 : 0 ))

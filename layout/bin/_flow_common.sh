# layout/bin/_flow_common.sh -- shared KLT/PDK/record-id boilerplate for the
# `layout/**/run-flow*.sh` scripts (layout/bin/run-trivial-cell-flow.sh,
# layout/cdac-array/bin/run-flow.sh, layout/comparator/bin/run-flow.sh,
# layout/sar-sequencer/bin/run-flow.sh). Meant to be `source`d, not executed
# directly, matching the `layout/bin/_*` naming convention `_record_common.py`
# already established for a shared, non-`run-flow`-named helper file (#118).
#
# Each function below infers the calling script's own name from
# `${BASH_SOURCE[1]}` (the caller's frame, one level up from this file) for
# its error-message prefix, so every flow script keeps its own name in its
# error output without having to pass it explicitly.
#
# `OUT_DIR`/`mkdir -p` construction is deliberately left to each caller: three
# of the four scripts write a flat `$SUBBLOCK_DIR/reports/$RECORD_ID`, but
# layout/sar-sequencer/bin/run-flow.sh's differs (`mkdir -p
# "$OUT_DIR/.klt/place-and-route"`), so folding that in here would force a
# parameter just to express one script's exception.

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

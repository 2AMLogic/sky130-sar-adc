#!/usr/bin/env bash
# Render (or verify) this block's T1 tier verdict with `klt signoff --manifest`.
#
#   bash signoff/run-signoff.sh           # regenerate signoff/t1-report.json
#   bash signoff/run-signoff.sh --check   # fail if the committed report drifted
#
# `--check` is what CI runs, and it is the whole reason the report is committed
# at all: a manifest that cites an evidence artifact which has since changed (a
# re-run DRC, a regenerated characterization report, an edited manifest) grades
# differently, and the drift turns the build red instead of the verdict quietly
# rotting into a stale prose claim. That rot is the failure mode issue #345 was
# filed against.
#
# It uses `klt signoff --check` rather than a byte-diff of a fresh render: the
# report's `build` block names how THIS install was provisioned, so two
# legitimate installs of the same pinned version can disagree on it byte-for-
# byte while grading identically (klayout-tools#2249). `--check` excludes
# exactly that block and compares everything else.
#
# GRADER PIN. `signoff/requirements.txt` pins the klt build that grades this
# manifest, and it deliberately DIVERGES from layout/requirements.txt's pin
# (which gates the DRC/LVS/compose flows that MINT the evidence, and only moves
# with a full re-run of every layout/ flow). Grading is a pure JSON + Markdown
# transform -- no PDK, no KLayout engine, no GDS read -- so it follows the
# grader release independently. The pin matters: the report records the
# checklist it graded against by content hash (`source_doc_content_hash`), and
# the T1 checklist grew an eleventh item on 2026-09-17, so an unpinned grader
# would silently change the verdict's denominator.
#
# Run from anywhere: `klt` is invoked FROM the repo root so the manifest's
# relative evidence paths mean the same thing here, in CI, and on a reviewer's
# machine. Override the interpreter with KLT=/path/to/klt.
#
# Exit codes:
#   0  report written (default mode), or the committed report still holds (--check)
#   1  the committed report drifted (--check), or the manifest/evidence is bad
#   2  `klt` is not installed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="signoff/block-manifest.json"
REPORT="signoff/t1-report.json"
PINNED_VERSION="0.6.0"

mode="write"
case "${1-}" in
"") ;;
--check) mode="check" ;;
-h | --help)
  sed -n '2,37p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
  ;;
*)
  echo "error: unknown argument '$1' (expected --check or nothing)" >&2
  exit 1
  ;;
esac

cd "$REPO_ROOT"

KLT="${KLT:-klt}"
if ! command -v "$KLT" >/dev/null 2>&1; then
  echo "error: '$KLT' not found on PATH -- install the pinned grader with:" >&2
  echo "         python3 -m venv .venv-signoff" >&2
  echo "         .venv-signoff/bin/pip install -r signoff/requirements.txt" >&2
  echo "         KLT=.venv-signoff/bin/klt bash signoff/run-signoff.sh ${1-}" >&2
  exit 2
fi

resolved_version="$("$KLT" --version 2>&1 | awk '{print $NF}')"
echo "klt: $(command -v "$KLT") (${resolved_version})" >&2
if [ "$resolved_version" != "$PINNED_VERSION" ]; then
  echo "warning: grader is ${resolved_version}, signoff/requirements.txt pins ${PINNED_VERSION}." >&2
  echo "         A different build may grade differently; CI uses the pin." >&2
fi

if [ "$mode" = "check" ]; then
  # `klt signoff --check`: exits 0 when the committed report still reproduces,
  # 3 when it drifted, 1 when the committed report is missing/unparseable.
  status=0
  "$KLT" signoff --manifest "$MANIFEST" --check "$REPORT" --format text --no-color || status=$?
  case "$status" in
  0)
    echo "$REPORT is current." >&2
    exit 0
    ;;
  3)
    echo >&2
    echo "error: $REPORT no longer matches a fresh grading of $MANIFEST." >&2
    echo "       Regenerate it with:  bash signoff/run-signoff.sh" >&2
    echo "       and read signoff/README.md before updating any claim it backs --" >&2
    echo "       a row that changed verdict is a change to this block's T1 claim." >&2
    exit 1
    ;;
  *)
    echo "error: klt signoff --check exited $status (manifest or evidence unreadable)" >&2
    exit 1
    ;;
  esac
fi

# Render. `klt signoff --manifest` exits 0 only for a block that has reached T1
# and 3 for "graded fine, at least one item unmet" -- the documented mid-ladder
# state, and this block's honest state today. Anything else is a tool or input
# error and must not be written out as if it were a verdict.
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
status=0
"$KLT" signoff --manifest "$MANIFEST" --format json >"$tmp" || status=$?
case "$status" in
0 | 3) ;;
*)
  echo "error: klt signoff exited $status -- not a tier verdict" >&2
  cat "$tmp" >&2
  exit 1
  ;;
esac

cp "$tmp" "$REPORT"
echo "wrote $REPORT (klt signoff exit $status; 3 = tier null, gaps open)" >&2

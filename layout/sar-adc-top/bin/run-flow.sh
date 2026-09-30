#!/usr/bin/env bash
# layout/sar-adc-top/bin/run-flow.sh -- place, route and verify the
# top-level SAR ADC assembly (issue #103), recording a timestamped,
# append-only report under layout/sar-adc-top/reports/<record-id>/,
# mirroring layout/trivial-cell/reports/'s own convention (see
# layout/README.md).
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/sar-adc-top/bin/run-flow.sh   # ~1 minute
#
# Requires: layout/.venv (see setup-venv.sh), a resolvable sky130A PDK
# install (same pin as sim/pdk.json), and each of the five sub-blocks'
# reports/LATEST to point at a real, already-committed record (#99-#102,
# #166) -- this flow *reads* those GDS files, it does not regenerate them.
#
# Runs entirely on the pinned `layout/.venv/bin/klt` (klayout-tools==0.6.0
# since 2026-09-23, `layout/requirements.txt`) -- no env override needed. Step 7's `klt
# extract --pin-source-cells` (klayout-tools#1515) previously required a
# `klt` build newer than the then-pinned 0.4.0, reached only via a
# `SAR_ADC_TOP_KLT` env-var override; that override is retired now that
# klayout-tools v0.5.0 (published 2026-09-15) carries the fix in the
# officially pinned build -- see layout/sar-adc-top/README.md's
# "Provenance" section and layout/requirements.txt's own header for the
# full trace.
#
# Flow (see layout/sar-adc-top/README.md for the full floorplan/routing
# writeup this implements):
#   1. Copy each sub-block's own reports/LATEST top GDS in as this flow's
#      own input (named <block>.gds -- what build_layout.py's own
#      `blocks[].cell` request entries expect).
#   2. build_layout.py    -- floorplan + route: emits the `klt draw` request
#                            for every wire/via/label this assembly's own
#                            interconnect needs, and the `klt gen-compose`
#                            explicit-placement request naming all five
#                            sub-blocks plus the FOUR decoupling-capacitor unit
#                            cells of issue #440/DR-017 (as `blocks[].cell`
#                            entries, #1189) plus this script's own new `route`
#                            cell. Also emits `decap.request.json` for step 2b.
#   2b. `klt gen cap_array` -- the one 46.9 um MiM unit cell those four
#                            placements share, plus `--verify-decap`, which
#                            asserts the generator's own reported bbox/ports
#                            still match the placement tables.
#   3. `klt draw`          -- writes the routing cell verbatim, named
#                            SAR_ADC_TOP_ROUTE (not the generic ROUTE every
#                            other `bin/build_layout.py` flow in this repo
#                            uses) so it never collides with `comparator`'s
#                            or `sampling_frontend`'s own internal ROUTE
#                            cell once all five GDS files are merged -- see
#                            "LVS pin declaration: resolved" in README.md.
#   4. `klt gen-compose`   -- places the five sub-blocks + the four decap unit
#                            cells + the routing cell into one composed cell.
#                            No `routing` block:
#                            this flow does its own routing (see
#                            build_layout.py's docstring for why).
#   5. `klt drc`           -- the composed layout must be CLEAN.
#   6. `klt extract` (unfiltered) -- a full-hierarchy extraction with no
#      declared-pin restriction, used only to *verify connectivity by net*
#      (every intended net's own device membership, checked by hand against
#      the intended schematic -- see record.md) -- not a `klt lvs` input.
#   7. `klt extract --pin-source-cells route__SAR_ADC_TOP_ROUTE` + `klt lvs`
#      -- the actual signoff attempt. `--pin-source-cells` (klayout-tools#1515)
#      resolves this flow's own 19 external-pin labels (all drawn directly in
#      this step's own SAR_ADC_TOP_ROUTE cell, by position, not by name) to
#      real top-level pins and demotes everything else -- reaching exactly
#      19/19/19 promoted/reference/matched pins, closing klayout-tools#1513.
#      Between the two, restore-cap-device-class.py re-attaches each `C`
#      card's own extractor-reported device class (klayout-tools#1876's local,
#      self-retiring workaround -- see that script's docstring), writing a
#      separate `sar_adc_top.extract.lvs.spice` and leaving the extractor's
#      own `sar_adc_top.extract.spice` in the record untouched.
#      `klt lvs` itself still reports a mismatch, but now for exactly one
#      remaining reason (klayout-tools#1878): see record.md and README.md's
#      "LVS device/topology blocker" section.
#  7b. `probe-decap-sites.py` -- the two questions about DR-017's decoupling
#      placement no verdict above can answer (issue #440): whether the
#      met3/met4 field its area budget assumes was free, measured against the
#      previous record's own GDS, and the lumped series resistance each of the
#      four ties adds, from the PDK's own sheet/via resistances. Writes
#      `decap-ties.json`, and HARD-FAILS if its resistance model no longer
#      matches the rectangles build_layout.py drew.
#
# Exit codes: 0 if DRC is clean (this flow's own current hard gate -- LVS is
# recorded whatever it reports, per the still-open LVS device/topology
# blocker (see README.md), not asserted here); 1 otherwise. `klt drc` exits 3
# on violations found (not "did not run"), so it is `|| true`-guarded and the
# verdict is asserted from the JSON envelope by render-record.py, never from
# an exit code (matching every other flow in this directory).
set -euo pipefail

TOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$TOP_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="$LAYOUT_DIR/.venv/bin/klt"
PDK_VARIANT=sky130A
TOP=gen_compose_0
ROUTE_CELL_NAME=SAR_ADC_TOP_ROUTE
# The literal cell name `klt gen-compose` gives this flow's own routing cell
# once merged into the composed GDS -- deterministic `"<block-id>__<cell-name>"`
# (docs/cli/gen-compose.md, issue #1189), not merge-order-dependent. The
# compose request below names this block "route".
ROUTE_CELL_QUALIFIED="route__${ROUTE_CELL_NAME}"

source "$LAYOUT_DIR/bin/_flow_common.sh"

require_klt "$KLT"
require_pdk "$KLT" "$PDK_VARIANT"

RECORD_ID="$(new_record_id "$REPO_ROOT")"
OUT_DIR="$TOP_DIR/reports/$RECORD_ID"
# The record `reports/LATEST` names RIGHT NOW -- read before this run overwrites
# it at the end. `probe-decap-sites.py` (step 7b) uses it as the baseline its
# free-field arm measures against; that arm is only meaningful when the baseline
# predates the decoupling placement, which the probe DETECTS (a `capm` plate
# already inside one of the sites) rather than assumes, so a baseline that
# already carries the pair reports an inconclusive arm instead of a false
# verdict. Override with `DECAP_BASELINE_RECORD=<record-id>` to re-measure
# against a specific earlier record -- which is what issue #440's own README
# numbers do, against the last pre-placement record.
PREV_RECORD="${DECAP_BASELINE_RECORD:-$(cat "$TOP_DIR/reports/LATEST" 2>/dev/null || true)}"
mkdir -p "$OUT_DIR"
echo "run-flow.sh: record $RECORD_ID -> $OUT_DIR"

# --- 1. Pull in each sub-block's own reports/LATEST top GDS ----------------
declare -A BLOCK_GDS=(
  [cdac_array]="cdac-array/cdac_array.gds"
  [sampling_frontend]="sampling-frontend/sampling_frontend.gds"
  [comparator]="comparator/comparator.gds"
  [sar_sequencer]="sar-sequencer/sar_sequencer.gds"
  [seln_inverters]="seln-inverters/seln_inverters.gds"
)
for block in "${!BLOCK_GDS[@]}"; do
  rel="${BLOCK_GDS[$block]}"
  subdir="${rel%%/*}"
  fname="${rel#*/}"
  latest="$(cat "$LAYOUT_DIR/$subdir/reports/LATEST")"
  cp "$LAYOUT_DIR/$subdir/reports/$latest/$fname" "$OUT_DIR/${block}.gds"
done

# --- 2. Floorplan + route ---------------------------------------------------
python3 "$TOP_DIR/bin/build_layout.py" "$OUT_DIR"

# --- 2b. Generate the on-die decoupling unit cell (issue #440, DR-017) ------
# DR-017 sizes one sky130_fd_pr__cap_mim_m3_1 per supply domain at
# W = L = 46.9 um, MF = 2. `MF = 2` is drawn here as what it is: TWO matched
# 46.9 um unit cells per domain, i.e. FOUR placements of this one generated
# cell, whose own placement offsets and ties live in build_layout.py's
# DECAP_OFFSETS / decoupling_caps().
#
# The generator is `klt gen cap_array` at num=1 -- the same generator, at the
# same plate size, that layout/sampling-frontend/ already ships DRC-clean for
# its own Csamp_{p,n} (that block's bin/gen_blocks.py CAP_DEVICES), which is
# why this composer draws no capm/via3 stack of its own. Params come from
# build_layout.py's own DECAP_GEN_PARAMS via decap.request.json (step 2), so
# the geometry that is placed and the geometry that is generated cannot be
# sourced from two different numbers -- and `--verify-decap` then asserts the
# generator's own reported bbox/ports against the placement tables, so a klt
# bump that moves the cell fails HERE instead of silently mis-tieing four
# capacitors.
( cd "$OUT_DIR" && "$KLT" gen cap_array --pdk "$PDK_VARIANT" \
    --params decap.request.json --cell-name DECAP_UNIT \
    -o decap_unit.gds --format json > decap.json )
python3 "$TOP_DIR/bin/build_layout.py" --verify-decap "$OUT_DIR/decap.json"

# --- 3. Draw every wire, via and label --------------------------------------
( cd "$OUT_DIR" && "$KLT" draw --params draw.request.json --cell-name "$ROUTE_CELL_NAME" \
    -o route.gds --format json > draw.json )

# --- 4. Place the five sub-blocks + the routing cell into one composed cell
( cd "$OUT_DIR" && "$KLT" gen-compose compose.request.json --format json > compose.json )
if [[ ! -f "$OUT_DIR/${TOP}.gds" ]]; then
  echo "run-flow.sh: gen-compose did not write ${TOP}.gds -- see compose.json" >&2
  cat "$OUT_DIR/compose.json" >&2
  echo "$RECORD_ID" > "$TOP_DIR/reports/LATEST"
  exit 1
fi
mv "$OUT_DIR/${TOP}.gds" "$OUT_DIR/sar_adc_top.gds"
GDS="$OUT_DIR/sar_adc_top.gds"
# Every `klt` verb records the input path it was INVOKED with, verbatim, as its
# envelope's own `file` field. Invoking with an absolute path therefore bakes
# this machine's `.loom/worktrees/issue-N/...` into committed evidence, and a
# grader on any other checkout (CI, a reviewer, this repo's own `main` after the
# worktree is reaped) cannot resolve it -- `klt signoff` reports
# `input_verified: null` for such a citation, and, worse, reports `true` on the
# ONE machine where the path still happens to exist, so a report rendered there
# drifts against CI's re-render of the same manifest (measured on issue #355).
# Passing a REPO-RELATIVE path from the repo root fixes both: the recorded path
# resolves from any checkout, and `input_verified` is `true` everywhere.
REL_GDS="${GDS#"$REPO_ROOT"/}"

# --- 5. DRC on the composed layout: must be CLEAN --------------------------
( cd "$REPO_ROOT" && "$KLT" drc "$REL_GDS" --deck sky130 --format json ) \
    > "$OUT_DIR/drc.json" || true

# --- 6. Unfiltered extraction: connectivity verification, not an LVS input -
( cd "$REPO_ROOT" && "$KLT" extract "$REL_GDS" --deck sky130 --top "$TOP" \
    -o "$OUT_DIR/sar_adc_top.extract.unfiltered.spice" --format json ) \
    > "$OUT_DIR/extract.unfiltered.json" || true

# --- 7. Signoff attempt: `--pin-source-cells` declared pins + LVS ----------
# `--pin-source-cells` (klayout-tools#1515) resolves this flow's own 19
# top-level pin labels -- every one of them drawn directly in this step's own
# SAR_ADC_TOP_ROUTE cell (built in step 3), at each label's own real
# position, never by name -- to the real net at that position, and demotes
# every other promoted pin. This closes klayout-tools#1513 (see
# README.md "LVS pin declaration: resolved"): it reaches exactly this
# design's own intended 19/19/19 promoted/reference/matched pin counts,
# where none of `--top-cell-pins`/`--pins`/`--def-pins` could. Requires a
# `klt` build with klayout-tools#1515 -- carried by every pinned release
# since `klayout-tools==0.5.0` (layout/requirements.txt).
( cd "$REPO_ROOT" && "$KLT" extract "$REL_GDS" --deck sky130 --top "$TOP" \
    --pin-source-cells "$ROUTE_CELL_QUALIFIED" \
    -o "$OUT_DIR/sar_adc_top.extract.spice" --format json ) \
    > "$OUT_DIR/extract.json" || true

# klayout-tools#1876 workaround: `klt extract`'s SPICE writer no longer emits
# a `C` card's device-class token (klayout-tools#1558/#1564's own correct
# simulatability fix), and this flow's pre-extracted `layout.netlist` LVS
# shape needs that class name to survive the SPICE round-trip. Re-attach each
# card's own extractor-reported class from `klt extract`'s own per-instance
# comment line, into a SEPARATE netlist -- `sar_adc_top.extract.spice` stays
# byte-for-byte what `klt extract` wrote, and the transformation is a
# one-token-per-`C`-card diff anyone can audit. Self-retiring: the script is a
# no-op (`restored: 0` in capclass.json) on any `klt` build that writes the
# token again. See restore-cap-device-class.py's docstring for the full trace.
# Still load-bearing on klayout-tools==0.6.0: upstream fixed #1876 on the
# *reader* side (#1921, so the extractor still writes bare cards and
# capclass.json will never report `noop: true`), but that reader keys its
# recovery on the `.SUBCKT` name case-sensitively while KLayout upper-cases
# it, so it recovers 0 of this netlist's 1028 caps (klayout-tools#2397).
# Measured: dropping this step takes the verdict from 98 back to 124
# mismatches. Retire it once #2397 is fixed and that measurement is re-run.
python3 "$TOP_DIR/bin/restore-cap-device-class.py" \
  "$OUT_DIR/sar_adc_top.extract.spice" \
  -o "$OUT_DIR/sar_adc_top.extract.lvs.spice" \
  --format json > "$OUT_DIR/capclass.json"

python3 "$TOP_DIR/bin/generate-lvs-reference.py" \
  --sar-sequencer-report "$LAYOUT_DIR/sar-sequencer/reports/$(cat "$LAYOUT_DIR/sar-sequencer/reports/LATEST")" \
  --seln-inverters-report "$LAYOUT_DIR/seln-inverters/reports/$(cat "$LAYOUT_DIR/seln-inverters/reports/LATEST")" \
  -o "$OUT_DIR/sar_adc_top.lvs-reference.spice"

# `combine_devices: true`: three of the five already-independently-verified
# sub-blocks (comparator, sar_sequencer, seln_inverters) need it to re-lump
# their own genuinely split/interleaved layout legs to match their own
# reference's lumped devices; the other two (cdac_array, sampling_frontend)
# need it FALSE (cdac_array to avoid klayout-tools#1497's parallel-cap
# combine nondeterminism; sampling_frontend has nothing to fold, so it is a
# no-op either way at that sub-block's own scope). `klt lvs`'s
# `options.combine_devices` is a single flag over the whole (flattened)
# compared netlist -- no per-subcircuit scoping exists -- so no single
# top-level setting can satisfy every already-independently-verified
# sub-block's own requirement simultaneously; `true` was measured to
# produce fewer, more analyzable mismatches (98) than `false` (2197).
#
# Three further shapes were measured against this same composed GDS and are
# all worse, so the single whole-request `true` stands (see README.md's "LVS
# device/topology blocker" section for the full trace):
#   - `combine_devices_per_circuit` (klayout-tools#1556): 1154 mismatches --
#     no per-macro subcircuit exists on the necessarily-flat layout side
#     (klayout-tools#1878, extraction has no hierarchical mode, #1085).
#   - class-scoped `combine_devices: ["NFET","PFET"]` (klayout-tools#1370):
#     126 mismatches, identical device matching (794) -- device class cannot
#     separate the FET legs that need folding (seln_inverters) from the ones
#     that must not be folded (sampling_frontend), since both are FETs.
#   - `klt lvs`'s inline-extraction shape (`layout.file`, which would sidestep
#     klayout-tools#1876's SPICE round-trip entirely): 2199 mismatches and
#     `device.combine_incomplete` -- it compares the *raw* extracted netlist
#     (1893 devices), on which `Netlist.combine_devices()` exhausts its retry
#     budget, where the pre-extracted shape starts from `klt extract`'s own
#     already-folded 869 devices.
# Filed generically at 2AMLogic/klayout-tools#1552 (closed) -> #1878.
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "netlist": "sar_adc_top.extract.lvs.spice", "top": "$TOP" },
  "reference": { "netlist": "sar_adc_top.lvs-reference.spice", "top": "sar_adc_top" },
  "options": { "combine_devices": true, "flatten_reference": true }
}
EOF
( cd "$OUT_DIR" && "$KLT" lvs lvs.request.json --format json > lvs.json ) || true

# --- 7b. Decoupling real estate + tie resistance (issue #440, DR-017) -------
# Neither `klt drc` (shapes) nor `klt erc` (connectivity, no resistance model)
# nor `klt lvs` (a pre-existing mismatch here) can answer either of DR-017's two
# standing questions about the placement: was the met3/met4 field its area
# budget assumes actually free, and how much series resistance does each tie add
# between a capacitor and the rail it decouples. This probe answers both by
# measurement, and FAILS THE FLOW if its resistance model no longer matches the
# rectangles `build_layout.py` actually drew -- so the README's numbers cannot
# quietly drift away from the layout they describe.
DECAP_BASELINE_ARG=()
if [ -n "$PREV_RECORD" ] && [ -f "$TOP_DIR/reports/$PREV_RECORD/sar_adc_top.gds" ]; then
  DECAP_BASELINE_ARG=(--baseline "$TOP_DIR/reports/$PREV_RECORD")
fi
python3 "$TOP_DIR/bin/probe-decap-sites.py" \
  --record "$OUT_DIR" "${DECAP_BASELINE_ARG[@]}" --format json \
  > "$OUT_DIR/decap-ties.json"

# --- 8. Record summary -------------------------------------------------
set +e
python3 "$TOP_DIR/bin/render-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" \
  > "$OUT_DIR/record.md"
record_status=$?
set -e

echo "$RECORD_ID" > "$TOP_DIR/reports/LATEST"
echo "run-flow.sh: done. See $OUT_DIR/record.md"
exit "$record_status"

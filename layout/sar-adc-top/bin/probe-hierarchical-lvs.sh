#!/usr/bin/env bash
# layout/sar-adc-top/bin/probe-hierarchical-lvs.sh -- measure whether
# klayout-tools#2722's hierarchical `klt extract --hierarchical-cells`
# (unlocking `options.combine_devices_per_circuit` on the LAYOUT side) clears
# issue #103's whole-netlist LVS mismatch, and what that mismatch actually is.
# Writes a NEW, append-only probe record under
# layout/sar-adc-top/probe-reports/<UTC-timestamp>-<short-sha>/ and never
# touches a flow record (reports/<id>/), which stay immutable evidence.
#
# Usage:
#   HIER_KLT=/path/to/klt layout/sar-adc-top/bin/probe-hierarchical-lvs.sh \
#       layout/sar-adc-top/reports/<record-id>
#
# HIER_KLT must be a `klt` whose `extract --help` lists `--hierarchical-cells`
# (merged upstream 2026-10-11 as klayout-tools#3096; NOT in the 0.7.0 release
# published 2026-10-08, so a throwaway venv built from a klayout-tools git SHA
# is the only way to reach it today). The script refuses to run otherwise.
# No flow record is minted and the pin in layout/requirements.txt is untouched.
#
# Five measurements, all on the GDS of the record named on the command line:
#   A  hierarchical extract + per-circuit combine  vs  the REAL reference
#   B  hierarchical extract + per-circuit combine  vs  DIAGNOSTIC reference
#   C  flat extract + whole-request combine_devices vs  DIAGNOSTIC reference
#   D  flat extract + whole-request combine_devices vs  the REAL reference
#      (== run-flow.sh step 7, re-run on this build so A..D share one tool)
# The DIAGNOSTIC reference is the real one with the top-level `GND` net
# renamed to `VGND` inside `.SUBCKT sar_adc_top` only. It models exactly the
# merge DR-012 records (bulk sky130 offers no way to split the shared
# p-substrate) and nothing else; it is NOT a signoff reference.
set -euo pipefail

RECORD="${1:?usage: $0 <path to layout/sar-adc-top/reports/<record-id>>}"
TOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYOUT_DIR="$(cd "$TOP_DIR/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
KLT="${HIER_KLT:?set HIER_KLT to a klt build carrying --hierarchical-cells}"
export PDK=sky130A
TOP=gen_compose_0
ROUTE_CELL_QUALIFIED="route__SAR_ADC_TOP_ROUTE"
HIER_CELLS="cdac_array__cdac_array,sar_sequencer__sar_sequencer,top_glue__top_glue,comparator__gen_compose_0,sampling_frontend__gen_compose_0,halflsb_offset__gen_compose_0"

"$KLT" extract --help | grep -q -- '--hierarchical-cells' || {
  echo "probe-hierarchical-lvs.sh: $KLT has no --hierarchical-cells" >&2; exit 2; }

source "$LAYOUT_DIR/bin/_flow_common.sh"
RECORD="$(cd "$RECORD" && pwd)"
PROBE_ID="$(new_record_id "$REPO_ROOT")"
OUT="$TOP_DIR/probe-reports/$PROBE_ID"
mkdir -p "$OUT"
cp "$RECORD/sar_adc_top.lvs-reference.spice" "$OUT/"
"$KLT" --version > "$OUT/klt-version.txt"
basename "$RECORD" > "$OUT/source-record.txt"
# The GDS is read in place (repo-relative, so the recorded path resolves on any
# checkout) rather than copied: it is the source record's own immutable file.
REL_GDS="${RECORD#"$REPO_ROOT"/}/sar_adc_top.gds"

# Diagnostic reference: GND -> VGND, inside the top-level subckt only.
python3 -I - "$OUT/sar_adc_top.lvs-reference.spice" "$OUT/reference.diag-gnd-eq-vgnd.spice" <<'EOF'
import re, sys
lines = open(sys.argv[1]).read().split("\n")
i = next(k for k, l in enumerate(lines) if l.startswith(".SUBCKT sar_adc_top"))
out = lines[: i + 1]
for l in lines[i + 1 :]:
    if not l.startswith("*"):
        l = re.sub(r"(?<![\w])GND(?![\w])", "VGND", l)
    out.append(l)
open(sys.argv[2], "w").write("\n".join(out))
EOF

extract() {  # extract <tag> [extra klt args...]
  local tag="$1"; shift
  ( cd "$REPO_ROOT" && "$KLT" extract "$REL_GDS" --deck sky130 --top "$TOP" \
      --pin-source-cells "$ROUTE_CELL_QUALIFIED" "$@" \
      -o "$OUT/$tag.extract.spice" --format json ) > "$OUT/$tag.extract.json" || true
  python3 "$TOP_DIR/bin/restore-cap-device-class.py" "$OUT/$tag.extract.spice" \
    -o "$OUT/$tag.extract.lvs.spice" --format json > "$OUT/$tag.capclass.json"
}
lvs() {  # lvs <name> <layout-spice> <reference-spice> <options-json>
  cat > "$OUT/$1.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "netlist": "$2", "top": "$TOP" },
  "reference": { "netlist": "$3", "top": "sar_adc_top" },
  "options": $4
}
EOF
  ( cd "$OUT" && "$KLT" lvs "$1.request.json" --format json > "$1.json" ) || true
}

extract flat
extract hier --hierarchical-cells "$HIER_CELLS"

# Per-circuit scoping: the same three-true / three-false split run-flow.sh's
# step-7 comment documents. Globs are case-sensitive and the SPICE reader
# upper-cases circuit names; the layout-side names carry the `<block>__`
# prefix klt gen-compose gave them, the reference-side names do not.
PER_CIRCUIT='{ "combine_devices_per_circuit": { "COMPARATOR*": true, "SAR_SEQUENCER*": true, "TOP_GLUE*": true, "CDAC_ARRAY*": false, "SAMPLING_FRONTEND*": false, "HALFLSB_OFFSET*": false }, "flatten_layout": true, "flatten_reference": true }'
WHOLE='{ "combine_devices": true, "flatten_reference": true }'
REF=sar_adc_top.lvs-reference.spice
DIAG=reference.diag-gnd-eq-vgnd.spice
lvs A-hier-real  hier.extract.lvs.spice "$REF"  "$PER_CIRCUIT"
lvs B-hier-diag  hier.extract.lvs.spice "$DIAG" "$PER_CIRCUIT"
lvs C-flat-diag  flat.extract.lvs.spice "$DIAG" "$WHOLE"
lvs D-flat-real  flat.extract.lvs.spice "$REF"  "$WHOLE"

python3 -I - "$OUT" <<'EOF' | tee "$OUT/summary.txt"
import collections, json, sys
out = sys.argv[1]
for name in ("A-hier-real", "B-hier-diag", "C-flat-diag", "D-flat-real"):
    d = json.load(open(f"{out}/{name}.json"))
    c = d["counts"]
    cats = collections.Counter(
        (m["category"], m["severity"]) for m in d["mismatches"])
    print(f"{name}: status={d['status']} devices={c['devices']['layout']}/"
          f"{c['devices']['reference']}/{c['devices']['matched']} "
          f"nets={c['nets']['layout']}/{c['nets']['reference']}/{c['nets']['matched']} "
          f"pins={c['pins']['layout']}/{c['pins']['reference']}/{c['pins']['matched']}")
    print("   " + ", ".join(f"{k[0]}[{k[1]}]={v}" for k, v in sorted(cats.items())))
EOF
echo "probe-hierarchical-lvs.sh: done -> $OUT"

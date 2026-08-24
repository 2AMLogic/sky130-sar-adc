#!/usr/bin/env bash
# regen_netlist.sh -- mechanical netlist regeneration for the SAR ADC
# top-level integration (issue #56).
#
# This is the concrete deliverable for #24's original AC3 / this issue's own
# AC4 ("regeneration is mechanical and checked"): it re-derives
# design/sar_adc_top.spice from the current design/*.sch hierarchy
# (design/sar_adc_top.sch instantiating design/sampling_frontend.sch #52,
# design/cdac/cdac_array.sch #53, design/comparator.sch #54, and
# design/sar_sequencer.sch #55) via the same xschem netlisting flow
# docs/environment-setup.md already documents, so "the netlist is
# demonstrably derived from the schematic, not hand-maintained" is a
# one-command, CI-checkable fact rather than a claim.
#
# Usage:
#   ./design/regen_netlist.sh            # regenerate design/sar_adc_top.spice in place
#   ./design/regen_netlist.sh --check    # regenerate to a scratch file and diff
#                                         # against the committed netlist; exit
#                                         # nonzero (staleness) if they differ
#
# Both modes also fail (nonzero exit) if any device instance in the
# regenerated netlist resolves to a non-ratified flavour (anything other
# than nfet_01v8/pfet_01v8/cap_mim_m3_1 sky130_fd_pr primitives or
# sky130_fd_sc_hd standard cells) -- DR-001's device-flavour gate, enforced
# mechanically rather than by review alone.
#
# Requires PDK_ROOT/PDK exported (source sim/env.sh first) and xschem on
# PATH -- exactly docs/environment-setup.md's bootstrap. `--check-env` is
# not implemented here; run sim/run_corners.py --check-env first if unsure
# the toolchain/PDK pin matches sim/toolchain.json / sim/pdk.json.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_SCH="${REPO_ROOT}/design/sar_adc_top.sch"
COMMITTED_NETLIST="${REPO_ROOT}/design/sar_adc_top.spice"
XSCHEMRC="${REPO_ROOT}/sim/xschemrc"

# The five schematic sources this netlist is derived from (order fixed, both
# for deterministic provenance-header content and for the flavour check).
SOURCE_SCH_FILES=(
  "design/sampling_frontend.sch"
  "design/cdac/cdac_array.sch"
  "design/comparator.sch"
  "design/sar_sequencer.sch"
  "design/sar_adc_top.sch"
)

CHECK_MODE=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=1
fi

if ! command -v xschem >/dev/null 2>&1; then
  echo "FAIL: xschem not found on PATH -- see docs/environment-setup.md" >&2
  exit 1
fi
if [[ -z "${PDK_ROOT:-}" || -z "${PDK:-}" ]]; then
  echo "FAIL: PDK_ROOT/PDK not set -- run 'source sim/env.sh' first" >&2
  exit 1
fi

SCRATCH_DIR="$(mktemp -d)"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

# xschem's own exit code reflects its electrical-rule check (e.g. the
# BPREF_P_NC/BPREF_N_NC/OUTN_NC/PH_B*/PH_EOC nets this integration
# deliberately leaves unconnected, per design/sar_adc_top.sch's own header
# "Known, named-not-closed integration gaps" section) -- NOT whether
# netlisting itself succeeded. This repo's existing convention (see
# design/comparator.sch's own header, and design/cdac/cdac_array.sch, which
# both already exit nonzero standalone for the same reason) is: a nonzero
# xschem exit with empty stdout/stderr and a complete device list is a
# clean netlist, not a netlisting failure -- so this script checks for the
# OUTPUT FILE's existence, not xschem's exit code, exactly like
# sim/sar-sequencer-behavioral/run_testbench.py's own netlist_dut() does
# (it only raises on a missing output file or actual stdout/stderr text).
set +e
XSCHEM_OUT="$(xschem -x -n -s -q --rcfile "${XSCHEMRC}" -o "${SCRATCH_DIR}" "${DESIGN_SCH}" 2>&1)"
set -e
RAW_NETLIST="${SCRATCH_DIR}/sar_adc_top.spice"
if [[ ! -f "${RAW_NETLIST}" ]]; then
  echo "FAIL: xschem did not produce ${RAW_NETLIST}" >&2
  echo "${XSCHEM_OUT}" >&2
  exit 1
fi
if [[ -n "${XSCHEM_OUT}" ]]; then
  echo "FAIL: xschem printed unexpected stdout/stderr text (expected none):" >&2
  echo "${XSCHEM_OUT}" >&2
  exit 1
fi

# --- Normalize machine-local absolute paths ------------------------------
# xschem embeds absolute `** sch_path:`/`** sym_path:` comment lines that
# encode wherever THIS machine's repo checkout happens to live -- not
# reproducible across machines/CI runners/worktrees. Rewrite them to a
# repo-relative path so the artifact (and the --check comparison below) is
# deterministic given the same schematic content, regardless of where the
# repo is checked out.
NORMALIZED_BODY="${SCRATCH_DIR}/normalized.spice"
sed -E "s#^(\\*\\* s(ch|ym)_path: ).*/(design/.*)#\\1\\3#" "${RAW_NETLIST}" > "${NORMALIZED_BODY}"

# --- Ratified-device-flavour gate (DR-001) -------------------------------
# Every device instance anywhere in the full hierarchy must be nfet_01v8 /
# pfet_01v8 / cap_mim_m3_1 (sky130_fd_pr) or sky130_fd_sc_hd (digital) --
# anything else (in particular any _g5v0d10v5 higher-voltage flavour, or a
# digital cell from a library other than sky130_fd_sc_hd) is a spec
# violation, not a design choice, per this issue's own acceptance criteria.
if grep -qE '_g5v0d10v5' "${NORMALIZED_BODY}"; then
  echo "FAIL: non-ratified _g5v0d10v5 device flavour found in the regenerated netlist:" >&2
  grep -nE '_g5v0d10v5' "${NORMALIZED_BODY}" >&2
  exit 1
fi
NON_HD_DIGITAL="$(grep -oE 'sky130_fd_sc_[a-zA-Z0-9]+__' "${NORMALIZED_BODY}" | sort -u | grep -v '^sky130_fd_sc_hd__$' || true)"
if [[ -n "${NON_HD_DIGITAL}" ]]; then
  echo "FAIL: non-sky130_fd_sc_hd digital cell library reference(s) found:" >&2
  echo "${NON_HD_DIGITAL}" >&2
  exit 1
fi
NON_PR_ANALOG="$(grep -oE 'sky130_fd_pr__[a-zA-Z0-9_]+' "${NORMALIZED_BODY}" | sort -u \
  | grep -vE '^sky130_fd_pr__(nfet_01v8|pfet_01v8|cap_mim_m3_1)$' || true)"
if [[ -n "${NON_PR_ANALOG}" ]]; then
  echo "FAIL: non-ratified sky130_fd_pr primitive(s) found (expected only nfet_01v8/pfet_01v8/cap_mim_m3_1):" >&2
  echo "${NON_PR_ANALOG}" >&2
  exit 1
fi
echo "OK: every device instance resolves to a ratified flavour (nfet_01v8/pfet_01v8/cap_mim_m3_1/sky130_fd_sc_hd)."

# --- Provenance header ----------------------------------------------------
# sha256 of each of the five source schematics this netlist is derived
# from -- deterministic given their content (unlike a wall-clock timestamp
# or a `git rev-parse HEAD`, which would drift on every unrelated commit
# elsewhere in the repo and make the --check comparison spuriously fail).
# A reviewer can independently reproduce these by hashing the same files.
PROVENANCE_FILE="${SCRATCH_DIR}/provenance.txt"
{
  echo "* sar_adc_top.spice -- full-hierarchy SAR ADC netlist (issue #56)."
  echo "* Regenerate with: ./design/regen_netlist.sh (requires PDK_ROOT/PDK, see"
  echo "* docs/environment-setup.md). CI fails (design/regen_netlist.sh --check,"
  echo "* wired into .github/workflows/ci.yml's pdk-smoke job) if this file does"
  echo "* not match a fresh regeneration from the current schematic sources --"
  echo "* staleness is failure (this issue's AC4)."
  echo "*"
  echo "* Provenance: sha256 of each source schematic this netlist derives from"
  echo "* (reproduce with: sha256sum <path>). This is the file-content hash, not"
  echo "* a git commit reference, so it stays meaningful in a shallow CI clone"
  echo "* and does not drift when an unrelated commit elsewhere touches HEAD."
  for f in "${SOURCE_SCH_FILES[@]}"; do
    HASH="$(sha256sum "${REPO_ROOT}/${f}" | cut -d' ' -f1)"
    echo "*   ${f}: sha256:${HASH}"
  done
  echo "*"
  echo "* Every device instance below is a ratified flavour (nfet_01v8/pfet_01v8/"
  echo "* cap_mim_m3_1 sky130_fd_pr primitives, or sky130_fd_sc_hd standard"
  echo "* cells) -- verified mechanically by this script, not by review alone."
} > "${PROVENANCE_FILE}"

FINAL_NETLIST="${SCRATCH_DIR}/final.spice"
cat "${PROVENANCE_FILE}" "${NORMALIZED_BODY}" > "${FINAL_NETLIST}"

if [[ "${CHECK_MODE}" -eq 1 ]]; then
  if [[ ! -f "${COMMITTED_NETLIST}" ]]; then
    echo "FAIL: ${COMMITTED_NETLIST} does not exist -- run without --check first." >&2
    exit 1
  fi
  if diff -u "${COMMITTED_NETLIST}" "${FINAL_NETLIST}"; then
    echo "OK: ${COMMITTED_NETLIST} matches a fresh regeneration from the current schematic sources."
    exit 0
  else
    echo "FAIL: ${COMMITTED_NETLIST} is STALE relative to the current schematic sources." >&2
    echo "      Run ./design/regen_netlist.sh (without --check) and commit the result." >&2
    exit 1
  fi
else
  cp "${FINAL_NETLIST}" "${COMMITTED_NETLIST}"
  echo "OK: wrote ${COMMITTED_NETLIST}"
fi

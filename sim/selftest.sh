#!/usr/bin/env bash
#
# Harness acceptance test.
#
#   sim/selftest.sh                unit tests + a reduced PVT/MC self-test run
#                                   (the "check:ci" default -- see below for why)
#   sim/selftest.sh --full         also runs the full corner grid + a larger MC N
#   sim/selftest.sh --quick        unit tests + environment check only, no ngspice
#   sim/selftest.sh --require-pdk  fail (instead of skipping) if the PDK is absent
#
# Stage 4 is the one that matters most: --sabotage-corners re-runs
# harness-corner-smoke with the process-corner .lib section forced to 'tt'
# and requires its process-axis sensitivity floor to FAIL. Stages 1-3 can
# all pass while the corner runner silently simulates typical everywhere --
# the numbers would look perfectly plausible and every downstream evidence
# record would be worthless.
#
# Provenance: structure ported from 2AMLogic/gf180-sar-adc's
# sim/selftest.sh (commit f613571aee5b80eff1eea37bdce9dfc88c5cf396), per
# CLAUDE.md's "Harness bootstrap" instruction. This repo has no ADC
# schematic yet, so the EXPERIMENTS list here is the two harness-proof
# circuits from issue #2 (harness-corner-smoke, mc-smoke), not gf180-sar-
# adc's ADC testbench suite -- see sim/README.md "Harness self-test
# experiments" for why, and for what a future ADC testbench adds.
#
# Timing note: each ngspice invocation against the sky130 combined model
# library costs roughly 15-20s on the reference toolchain (model-library
# load dominates, not simulation time) -- see sim/harness/runner.py's OAT
# design note. The default (non-quick, non-full) run below is 17 such
# invocations, ~5 minutes measured on the reference toolchain; --full is
# the complete corner grid plus a larger Monte Carlo N and is meant for a
# deliberate, periodic deeper pass. The default is what `npm run check:ci`
# runs; on a machine (or CI runner) without ngspice or the pinned PDK the
# simulation stages skip and it costs seconds instead. If the default ever
# needs to be cheaper, cut mc_n before cutting corners: stage 4's negative
# control needs at least two process corners to have anything to compare.
#
# Exit codes: 0 pass (or skipped sim stages), 1 something failed.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FULL=0
QUICK=0
REQUIRE_PDK=0
for arg in "$@"; do
  case "${arg}" in
    --full) FULL=1 ;;
    --quick) QUICK=1 ;;
    --require-pdk) REQUIRE_PDK=1 ;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: ${arg}" >&2; exit 1 ;;
  esac
done

run_corners() {
  python3 "${SIM_DIR}/run_corners.py" "$@"
}

run_mc() {
  python3 "${SIM_DIR}/monte_carlo.py" "$@"
}

echo "== 1/4 harness unit tests (no PDK required) =="
if ! python3 -m unittest discover -s "${SIM_DIR}/tests" -t "${SIM_DIR}/tests"; then
  echo "FAIL: harness unit tests"
  exit 1
fi

echo
echo "== 2/4 environment =="
# --check-env distinguishes its two failure modes, and so must we: exit 3
# means a tool is MISSING (skippable on a machine that has not been
# bootstrapped), exit 1 means everything is installed but a pinned version
# DRIFTED -- which is a real problem and must never be reported as "tools
# unavailable, skipping".
run_corners --check-env
env_status=$?
case "${env_status}" in
  0) ;;
  1)
    echo
    echo "FAIL: the installed toolchain does not match sim/toolchain.json."
    echo "      Simulation stages skipped deliberately: results from a drifted"
    echo "      toolchain are not comparable with the records already in sim/."
    exit 1
    ;;
  *)
    if [ "${REQUIRE_PDK}" -eq 1 ]; then
      echo "FAIL: ngspice and/or the sky130 PDK are not available"
      exit 1
    fi
    echo
    echo "SKIP: simulation stages -- ngspice and/or the sky130 PDK are not available."
    echo "      Unit tests passed. Install the PDK (see docs/environment-setup.md)"
    echo "      to run the end-to-end PVT and Monte Carlo stages."
    exit 0
    ;;
esac

if [ "${QUICK}" -eq 1 ]; then
  echo
  echo "SKIP: stages 3-4 (--quick: unit tests + environment check only)."
  echo
  echo "PASS (quick): harness plumbing is present; PVT/MC switching NOT verified."
  exit 0
fi

echo
echo "== 3/4 end-to-end PVT + Monte Carlo runs =="
if [ "${FULL}" -eq 1 ]; then
  corner_args=(harness-corner-smoke)
  mc_n=10
else
  corner_args=(harness-corner-smoke --corners tt,ss,ff --temps 27,125 --supply-tol 0.1)
  mc_n=4
fi

echo
echo "-- harness-corner-smoke --"
if ! run_corners "${corner_args[@]}"; then
  echo "FAIL: PVT run for harness-corner-smoke"
  exit 1
fi

echo
echo "-- mc-smoke (N=${mc_n}) --"
if ! run_mc mc-smoke --seed 1 --n "${mc_n}"; then
  echo "FAIL: Monte Carlo run for mc-smoke (including its negative control)"
  exit 1
fi

echo
echo "== 4/4 negative control: corner switching must be verifiable =="
echo "Re-running harness-corner-smoke with the process-corner .lib section"
echo "forced to 'tt'. The process-axis sensitivity floor MUST fail; a pass"
echo "here means the corner runner is not actually switching corners."
run_corners harness-corner-smoke --sabotage-corners \
  --corners tt,ss,ff --temps 27 --supply-tol 0 --quiet
sabotage_status=$?
case "${sabotage_status}" in
  1)
    echo "ok: harness-corner-smoke correctly FAILED under --sabotage-corners"
    ;;
  0)
    echo "FAIL: harness-corner-smoke PASSED with the process corner forced to 'tt'."
    echo "      Corner switching is not taking effect, or the sensitivity floor is"
    echo "      too weak to notice. Do not trust any evidence record from this"
    echo "      testbench until this is fixed."
    exit 1
    ;;
  *)
    echo "FAIL: harness-corner-smoke errored (exit ${sabotage_status}) under"
    echo "      --sabotage-corners instead of reporting a check failure; the"
    echo "      negative control is inconclusive."
    exit 1
    ;;
esac

echo
echo "PASS: harness is functional end to end; PVT corner switching and the"
echo "      Monte Carlo negative control are both verified."

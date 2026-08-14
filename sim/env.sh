# Source me:  source sim/env.sh
#
# Exports the sky130 PDK environment that the harness resolved, so that an
# interactive ngspice / xschem session sees exactly the same PDK the corner
# runner uses. Safe to source from any directory.
#
#   PDK_ROOT   parent of the variant dir (open_pdks convention)
#   PDK        variant, e.g. sky130A
#
# Provenance: ported from 2AMLogic/gf180-sar-adc's sim/env.sh
# (commit f613571aee5b80eff1eea37bdce9dfc88c5cf396), per CLAUDE.md's
# "Harness bootstrap" instruction -- gf180mcu-specific exports (GF180_*)
# dropped since sky130's harness has no equivalent per-variant metal-stack
# selection.

_sky130_env_self="${BASH_SOURCE[0]:-${(%):-%x}}"
_sky130_sim_dir="$(cd "$(dirname "${_sky130_env_self}")" && pwd)"

if _sky130_exports="$(python3 "${_sky130_sim_dir}/run_corners.py" --print-env)"; then
  eval "${_sky130_exports}"
  echo "sky130: PDK_ROOT=${PDK_ROOT} PDK=${PDK}"
else
  echo "sky130: PDK not found -- run 'python3 ${_sky130_sim_dir}/run_corners.py --check-env'" >&2
fi

unset _sky130_env_self _sky130_sim_dir _sky130_exports

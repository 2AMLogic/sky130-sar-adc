"""Shared Verilog/CDL flattening core for the layout sub-block
`generate-lvs-reference.py` scripts.

Used by `layout/sar-sequencer/bin/generate-lvs-reference.py` and
`layout/seln-inverters/bin/generate-lvs-reference.py`, which import this
module via a `sys.path` insert (see either script's own header) rather than a
package install, matching this directory's existing `_geometry_common.py` /
`_record_common.py` shared-module convention.

Houses the four functions that were byte-identical (modulo comments) between
those two scripts: a flat structural-Verilog parser, a CDL `.SUBCKT` ->
pin-list/M-card extractor, the nfet/pfet device-class generalizer, and the
`PDK_ROOT`/`PDK` env-var resolver. Each sub-block's own `CELL_TYPES`,
`top_ports`, and docstring stay defined on that sub-block's own script --
`parse_verilog_netlist`'s instance-matching regex is parameterized on a
``cell_types`` tuple (the caller's own module-level `CELL_TYPES`) rather than
hard-coded here, since it is genuinely per-block.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal

_MODULE_RE = re.compile(r"^module\s+(\w+)\s*\(", re.M)
_PORT_CONN_RE = re.compile(r"\.\s*(\w+)\s*\(\s*([^()]*?)\s*\)")


def parse_verilog_netlist(
    path: str, cell_types: tuple[str, ...]
) -> tuple[str, list[tuple[str, str, dict[str, str]]]]:
    """Parse a flat structural Verilog netlist into
    ``(top_module_name, instances)``, where ``instances`` is a list of
    ``(instance_name, cell_type, {signal_pin: net_or_None})`` -- ``None`` for
    an explicitly unconnected port (e.g. ``.Y()``), never an empty string.

    Deliberately narrow: only recognizes the standard-cell types in
    ``cell_types``, in the named-port-connection form every real
    synthesis/P&R tool (OpenROAD's own `write_verilog` included) emits.
    """
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    module_match = _MODULE_RE.search(text)
    if module_match is None:
        raise SystemExit(f"generate-lvs-reference.py: no 'module' found in {path}")
    top_name = module_match.group(1)

    instance_re = re.compile(
        r"\b(" + "|".join(re.escape(c) for c in cell_types) + r")\s+(\w+)\s*\((.*?)\)\s*;",
        re.S,
    )

    instances: list[tuple[str, str, dict[str, str]]] = []
    for cell_type, inst_name, port_list_text in instance_re.findall(text):
        pin_map: dict[str, str] = {}
        for port_name, connection in _PORT_CONN_RE.findall(port_list_text):
            connection = connection.strip()
            if connection:
                pin_map[port_name] = connection
        instances.append((inst_name, cell_type, pin_map))

    return top_name, instances


def _extract_cdl_subckt(cdl_text: str, name: str) -> tuple[list[str], list[tuple]]:
    pat = re.compile(rf"^\.SUBCKT {re.escape(name)} (.*?)\n(.*?)^\.ENDS", re.S | re.M)
    match = pat.search(cdl_text)
    if match is None:
        raise SystemExit(f"generate-lvs-reference.py: '{name}' not found in CDL")
    pins = match.group(1).split()
    lines = []
    current = ""
    for line in match.group(2).split("\n"):
        if line.startswith("*"):
            continue
        if line.startswith("+"):
            current += " " + line[1:].strip()
        else:
            if current:
                lines.append(current)
            current = line.strip()
    if current:
        lines.append(current)

    devices = []
    for line in lines:
        if not line.startswith("M"):
            continue
        toks = line.split()
        inst, drain, gate, source, body, model = toks[0], *toks[1:6]
        params = dict(t.split("=", 1) for t in toks[6:] if "=" in t)
        # `m=` is the CDL's own parallel-finger multiplier (e.g.
        # sky130_fd_sc_hd__buf_4's own output-stage MMIN2/MMIP2 devices are
        # drawn as `m=4` -- 4 identical fingers -- not `w=4x` in one finger;
        # its distinct `mult=` field is an unrelated LDD/stress-modeling
        # parameter, not a device count). `klt extract`'s `combine_devices`
        # folds those same 4 physically-drawn layout fingers into one
        # schematic-equivalent device with 4x the per-finger W (verified:
        # this sub-block's raw pre-fold device_count of 778 folds to exactly
        # 760 post-combine -- 18 fewer, matching 3 buf_4 instances x 2
        # multi-finger output-stage transistors x (m=4 - 1) redundant
        # fingers folded away). A reference M-card using the CDL's bare
        # per-finger `w=` instead of `w= * m` would understate that folded
        # device's true width 4x -- exactly the residual NetlistComparer
        # `device.unmatched`/`net.merged`/`net.split` mismatch this comment
        # fixes (issue #102's own investigation; see README.md "LVS
        # reference provenance").
        # `Decimal` (not `float`) so e.g. 0.65 * 4 prints as the exact `2.6`
        # a human/`klt` would write, not a binary-float artifact like
        # `2.6000000000000005`.
        w = Decimal(params["w"]) * int(Decimal(params.get("m", "1")))
        devices.append((inst, drain, gate, source, body, model, w, params.get("l")))
    return pins, devices


def _generalize_model(model: str) -> str:
    if "nfet" in model:
        return "nfet"
    if "pfet" in model:
        return "pfet"
    raise SystemExit(f"generate-lvs-reference.py: unrecognized model '{model}'")


def _resolve_pdk_root() -> str:
    root = os.environ.get("PDK_ROOT") or os.path.expanduser("~/.volare")
    variant = os.environ.get("PDK", "sky130A")
    return os.path.join(root, variant)

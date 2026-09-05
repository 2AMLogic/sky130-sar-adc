#!/usr/bin/env python3
"""Generate the CDAC sub-block's LVS reference netlists *from the schematic*
(issue #100).

`klt lvs` compares an extracted netlist against a reference SPICE netlist
written in the extraction deck's own device vocabulary. The schematic is the
authority here, so this script does not hand-author that reference: it runs
xschem headlessly over `design/cdac/cdac_array.sch` /
`design/cdac/cdac_unit_cell.sch`, parses the netlist xschem emits, and
rewrites each `X`-card into the corresponding deck-vocabulary card. No
topology is invented, reordered, or dropped along the way -- the rewrite is
purely a change of device vocabulary, and the script fails loudly on any
card it does not recognise rather than silently skipping it.

The three rewrites, and why each is a *vocabulary* change and not a design
statement:

1. `sky130_fd_pr__nfet_01v8` / `sky130_fd_pr__pfet_01v8` subcircuit calls
   become plain `M` cards on the deck's own `nfet` / `pfet` device classes,
   keeping L and W (the deck's MOS extractor reports exactly those two;
   `ad`/`as`/`pd`/`ps` and friends are xschem-computed stimulus parameters
   the layout extractor does not model, and are dropped).

2. `sky130_fd_pr__cap_mim_m3_1` with `MF=w` becomes `w` separate `C` cards,
   each of value `C_unit`, on the deck's `sky130_fd_pr__model__cap_mim`
   class -- one reference card per physically drawn unit capacitor, not one
   combined card of `w * C_unit` (issue #148). `design/cdac/README.md`
   states outright that `MF=w` is netlist-level shorthand for *w parallel
   unit cells*; the layout draws those `w` units literally, so `w` literal
   unit-value `C` cards is the *literal* translation, not a scaled
   stand-in. This also means the LVS request no longer needs
   `options.combine_devices` at all: issue #148 found that
   `klayout.db.Netlist.combine_devices()` does not reliably fold `w`
   identical-valued parallel capacitors into one correctly-summed device
   for `w` in the hundreds (it is documented as run-to-run nondeterministic
   for a *different* reason, klayout-tools#1185's partial-match
   `RuntimeError`, but issue #148's own investigation found a second,
   silent failure mode with no exception at all: the combined device's
   *primary* `C` parameter is left at a single input instance's unmerged
   value while the *secondary* `A`/`P` geometry parameters are correctly
   summed -- see `layout/cdac-array/README.md`'s "The matching strategy",
   `combine_devices()` section, for the full writeup). Comparing `w`
   drawn units against `w` reference units 1:1 sidesteps that code path
   entirely: `klt lvs` now performs a literal, uncombined device-for-device
   match, which is a *stronger* check than the folded comparison ever was
   (it needs no separate extracted-device-count verdict to prove the array
   is built from unit elements -- LVS itself now fails if it is not).
   `C_unit` is imported from `cdac_layout.py`, where it is derived from the
   drawn plate size and the extraction deck's own published area/perimeter
   coefficients.

3. The schematic's `VSS` (every nfet's bulk) becomes `vsubs`, the name
   `klt extract`'s sky130 deck gives the synthesized global substrate net
   it ties every nfet body to. This is a rename of one net, disclosed in
   the emitted file's header; sky130 has no drawn "VSS layer" for a block
   with no substrate tap of its own, so the extractor's global is the only
   thing the schematic's VSS *can* correspond to.

Usage:

    layout/cdac-array/bin/generate-lvs-reference.py [--check]

Writes `layout/cdac-array/reference/<top>.lvs-reference.spice` for both
tops. `--check` regenerates into memory and fails (exit 3) if the committed
file has drifted, so CI/the flow can prove the committed reference is still
what the schematic says.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CDAC_DIR = Path(__file__).resolve().parents[1]
LAYOUT_DIR = CDAC_DIR.parent
REPO_ROOT = LAYOUT_DIR.parent

_spec = importlib.util.spec_from_file_location(
    "cdac_layout", Path(__file__).resolve().parent / "cdac_layout.py"
)
assert _spec and _spec.loader
_cdac_layout = importlib.util.module_from_spec(_spec)
sys.modules["cdac_layout"] = _cdac_layout
_spec.loader.exec_module(_cdac_layout)

CAP_UNIT_F = _cdac_layout.CAP_UNIT_F
CAPM_SIDE = _cdac_layout.CAPM_SIDE

TOPS = ("cdac_array", "cdac_unit_cell")

MOS_MODELS = {
    "sky130_fd_pr__nfet_01v8": "nfet",
    "sky130_fd_pr__pfet_01v8": "pfet",
}
CAP_MODEL = "sky130_fd_pr__cap_mim_m3_1"
CAP_CLASS = "sky130_fd_pr__model__cap_mim"
SUBSTRATE_NET = "vsubs"


def netlist_schematic(top: str, outdir: Path) -> str:
    """Run xschem headlessly over `design/cdac/<top>.sch`."""
    sch = REPO_ROOT / "design" / "cdac" / f"{top}.sch"
    if not sch.is_file():
        raise SystemExit(f"generate-lvs-reference.py: no such schematic: {sch}")
    subprocess.run(
        [
            "xschem", "-x", "-n", "-s", "-q",
            "--rcfile", str(REPO_ROOT / "sim" / "xschemrc"),
            "-o", str(outdir),
            str(sch),
        ],
        capture_output=True,
        text=True,
        check=False,  # xschem exits non-zero even on a successful headless netlist
    )
    produced = outdir / f"{top}.spice"
    if not produced.is_file():
        raise SystemExit(f"generate-lvs-reference.py: xschem produced no {produced}")
    return produced.read_text()


def join_continuations(text: str) -> list[str]:
    """Fold SPICE continuation lines back into their card.

    xschem wraps long lines two different ways: an ordinary device card
    continues with a leading `+`, while the commented-out `**.subckt` pin
    list continues with a leading `*+`. Both must be folded, or a wide
    subcircuit silently loses the tail of its pin list.
    """
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.rstrip()
        cont = None
        if stripped.startswith("*+"):
            cont = stripped[2:]
        elif stripped.startswith("+"):
            cont = stripped[1:]
        if cont is not None:
            if not lines:
                raise SystemExit("generate-lvs-reference.py: continuation with no card")
            lines[-1] = lines[-1] + " " + cont.strip()
        else:
            lines.append(stripped)
    return lines


def device_name(prefix: str, name: str) -> str:
    """SPICE requires the device letter to lead; keep the schematic's own
    instance name when it already does (`M1` stays `M1`, not `MM1`)."""
    return name if name[:1].upper() == prefix else prefix + name


def parse_params(tokens: list[str]) -> dict[str, str]:
    return dict(
        (t.split("=", 1)[0].lower(), t.split("=", 1)[1]) for t in tokens if "=" in t
    )


def rewrite(top: str, netlist: str) -> str:
    lines = join_continuations(netlist)
    pins: list[str] = []
    cards: list[str] = []

    for line in lines:
        if line.startswith("**.subckt"):
            parts = line.split()
            if parts[1] != top:
                raise SystemExit(
                    f"generate-lvs-reference.py: expected .subckt {top}, got {parts[1]}"
                )
            pins = [SUBSTRATE_NET if p == "VSS" else p for p in parts[2:]]
            continue
        if not line.startswith("X"):
            continue
        tokens = line.split()
        name = tokens[0][1:]
        positional = [t for t in tokens[1:] if "=" not in t]
        params = parse_params(tokens[1:])
        model = positional[-1]
        nets = positional[:-1]

        if model in MOS_MODELS:
            if len(nets) != 4:
                raise SystemExit(f"generate-lvs-reference.py: bad MOS card: {line}")
            d, g, s, b = nets
            b = SUBSTRATE_NET if b == "VSS" else b
            cards.append(
                f"{device_name('M', name)} {d} {g} {s} {b} {MOS_MODELS[model]} "
                f"L={params['l']}U W={params['w']}U"
            )
        elif model == CAP_MODEL:
            if len(nets) != 2:
                raise SystemExit(f"generate-lvs-reference.py: bad cap card: {line}")
            weight = int(params.get("mf", "1"))
            # `w` literal unit-value `C` cards, not one combined card of
            # `w * C_unit` (issue #148): see this module's docstring, item 2,
            # for why a combined card requires `klt lvs`'s
            # `options.combine_devices`, and why that option is not reliable
            # for `w` in the hundreds. One drawn unit capacitor per card
            # keeps the comparison literal and needs no combining at all.
            base = device_name("C", name)
            for unit in range(weight):
                instance = base if weight == 1 else f"{base}_{unit}"
                cards.append(
                    f"{instance} {nets[0]} {nets[1]} {CAP_UNIT_F:.9e} {CAP_CLASS}"
                )
        else:
            raise SystemExit(
                f"generate-lvs-reference.py: unrecognised device model {model!r} "
                f"in {top}.sch -- refusing to drop it silently:\n  {line}"
            )

    if not pins:
        raise SystemExit(f"generate-lvs-reference.py: no .subckt line found for {top}")
    if not cards:
        raise SystemExit(f"generate-lvs-reference.py: no devices found for {top}")

    header = f"""* {top}.lvs-reference.spice -- GENERATED, do not edit by hand.
*
* Regenerate with: layout/cdac-array/bin/generate-lvs-reference.py
* Source of truth: design/cdac/{top}.sch (issue #53), netlisted headlessly
* by xschem and rewritten into `klt extract --deck sky130`'s own device
* vocabulary. See that script's docstring for the three rewrites and why
* each is a change of vocabulary rather than of topology.
*
* Unit capacitor: the schematic sizes the MiM plate W=L=1.8988 um; the
* drawn plate is the nearest 1 nm-grid square, {CAPM_SIDE} um, whose
* capacitance under the extraction deck's own published coefficients
* (area 2.0 fF/um^2, perimeter 0.19 fF/um) is
* C_unit = {CAP_UNIT_F:.9e} F. A bit of weight w carries `MF=w` in the
* schematic and w drawn unit capacitors in the layout, so its reference is
* w separate C cards of C_unit each -- one per physically drawn unit,
* compared 1:1 against the layout's own w extracted unit devices with no
* `klt lvs` `combine_devices` folding needed on either side (issue #148:
* `Netlist.combine_devices()` does not reliably re-sum w identical-valued
* parallel capacitors into one device for w in the hundreds).
*
* Substrate: the schematic's VSS (every nfet bulk) appears here as
* `{SUBSTRATE_NET}`, the name the sky130 extraction deck gives its
* synthesized global substrate net.
"""
    body = ".SUBCKT {} {}\n{}\n.ENDS {}\n".format(
        top, " ".join(pins), "\n".join(cards), top
    )
    return header + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail (exit 3) if the committed reference differs from a fresh regeneration",
    )
    args = parser.parse_args()

    outdir = CDAC_DIR / "reference"
    outdir.mkdir(parents=True, exist_ok=True)
    drifted = []
    with tempfile.TemporaryDirectory() as td:
        for top in TOPS:
            generated = rewrite(top, netlist_schematic(top, Path(td)))
            target = outdir / f"{top}.lvs-reference.spice"
            if args.check:
                current = target.read_text() if target.is_file() else ""
                if current != generated:
                    drifted.append(str(target))
                continue
            target.write_text(generated)
            print(f"wrote {target}")

    if drifted:
        print(
            "generate-lvs-reference.py: committed reference(s) differ from the "
            "schematic:\n  " + "\n  ".join(drifted),
            file=sys.stderr,
        )
        return 3
    if args.check:
        print("generate-lvs-reference.py: committed references match the schematic")
    return 0


if __name__ == "__main__":
    sys.exit(main())

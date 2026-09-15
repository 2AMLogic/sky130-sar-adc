#!/usr/bin/env python3
"""Restore the trailing device-class token on a `klt extract`-written SPICE
netlist's capacitor (`C`) cards -- a local, self-retiring workaround for
2AMLogic/klayout-tools#1876 (issue #103).

Why this exists
---------------
`layout/sar-adc-top/bin/run-flow.sh` compares a *pre-extracted* layout
netlist (`klt lvs`'s `layout.netlist` request shape) against this assembly's
hierarchical reference netlist. That shape round-trips the extracted netlist
through SPICE text, so every device's class identity has to survive as text.

klayout-tools#1558/#1564 (in `klayout-tools==0.5.0`) stopped writing a
trailing class-name token on `C` cards -- a correct, independently motivated
fix, because ngspice cannot simulate `C... <value> <class>`. Its side effect
on *this* LVS shape is that `NetlistSpiceReader` reading that bare card back
in can no longer recover the capacitor's real device class, so capacitor
devices stop resolving to the reference netlist's own explicitly-named
capacitor devices by class name. Filed generically as klayout-tools#1876.

What this does
--------------
`klt extract` still writes the device class of every extracted instance, in
that instance's own `* device instance <name> <orient> *<mult> <x>,<y>
<class>` comment line immediately above the card. This script copies that
class name -- the extractor's own statement of the device's class, not an
assumption made here -- onto the `C` card it annotates, reproducing byte-for-
byte the card shape `klt extract` itself wrote before #1558.

Deliberate properties:

* **Only `C` cards are touched.** A card of any other kind is copied
  verbatim, and every rewritten line is asserted to be a `C` card whose
  instance name matches the comment it took the class from.
* **Only a card that is actually missing the token is touched** (a card whose
  last field is not numeric already carries a class name). So this step is a
  **no-op** on any `klt` build that writes the token -- it retires itself
  automatically once klayout-tools#1876 is fixed upstream, with no flow
  change needed, and `restored == 0` in the JSON summary is the signal that
  that has happened.
* **The unmodified extraction is never overwritten.** run-flow.sh keeps
  `sar_adc_top.extract.spice` (exactly what `klt extract` wrote) in the
  record and writes this script's output alongside it as a separate,
  diffable artifact.

Usage
-----
    restore-cap-device-class.py <input.spice> -o <output.spice> [--format json]

Exit codes: 0 on success; 1 if the input violates the shape this script
requires (a `C` card missing its class token with no matching `* device
instance` comment above it) -- a signal that `klt extract`'s own output shape
changed and this workaround needs revisiting, never something to paper over.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

#: `klt extract`'s own per-instance provenance comment, e.g.
#: `* device instance $866 r0 *1 0,0.35 sky130_fd_pr__model__cap_mim`.
DEVICE_INSTANCE_RE = re.compile(
    r"^\*\s*device instance\s+(?P<name>\S+)\s+.*\s(?P<cls>\S+)\s*$"
)

#: A SPICE numeric field (the capacitance value a bare `C` card ends with).
NUMERIC_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?[a-zA-Z]*$")


def _is_numeric(field: str) -> bool:
    """True for a SPICE value field (`8.647288e-15`, `1.2P`), not a name."""
    return bool(NUMERIC_RE.match(field)) and not field.startswith("\\")


def restore(text: str) -> tuple[str, dict[str, object]]:
    """Return ``(rewritten_text, summary)`` for one extracted netlist."""
    out: list[str] = []
    pending: tuple[str, str] | None = None  # (instance name, device class)
    restored = 0
    c_cards = 0
    classes: Counter[str] = Counter()

    for lineno, line in enumerate(text.splitlines(), start=1):
        match = DEVICE_INSTANCE_RE.match(line)
        if match:
            pending = (match.group("name"), match.group("cls"))
            out.append(line)
            continue

        stripped = line.strip()
        if stripped.startswith("C") and not stripped.startswith("*"):
            c_cards += 1
            fields = stripped.split()
            instance = fields[0][1:]
            if _is_numeric(fields[-1]):
                # No trailing class token -- klayout-tools#1876's shape.
                if pending is None or pending[0] != instance:
                    print(
                        f"restore-cap-device-class.py: line {lineno}: `C` card "
                        f"{fields[0]} has no trailing device class and no "
                        "matching `* device instance` comment above it -- "
                        "`klt extract`'s output shape changed; revisit this "
                        "workaround (klayout-tools#1876) rather than guessing "
                        "a class name.",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)
                line = f"{line.rstrip()} {pending[1]}"
                restored += 1
                classes[pending[1]] += 1

        out.append(line)
        if not stripped.startswith("*"):
            pending = None

    summary: dict[str, object] = {
        "schema": "sar-adc-top.cap-device-class/1",
        "workaround_for": "2AMLogic/klayout-tools#1876",
        "c_cards": c_cards,
        "restored": restored,
        "restored_classes": dict(sorted(classes.items())),
        "noop": restored == 0,
    }
    return "\n".join(out) + "\n", summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="extracted SPICE netlist")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="netlist to write"
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="summary form"
    )
    args = parser.parse_args()

    rewritten, summary = restore(args.input.read_text())
    args.output.write_text(rewritten)
    summary["input"] = str(args.input)
    summary["output"] = str(args.output)

    if args.format == "json":
        print(json.dumps(summary, indent=2))
    elif summary["noop"]:
        print(
            "restore-cap-device-class.py: no-op -- every `C` card already "
            f"carries its device class ({summary['c_cards']} cards); "
            "klayout-tools#1876 appears fixed in this `klt` build."
        )
    else:
        print(
            f"restore-cap-device-class.py: restored the device-class token on "
            f"{summary['restored']}/{summary['c_cards']} `C` cards "
            f"({', '.join(summary['restored_classes'])})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

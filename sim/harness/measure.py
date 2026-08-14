"""Parse `let <name> = <expr>` / `print <name>` output from an ngspice batch
log into a {name: float} dict.

ngspice's `print <var>` (inside a .control block, after the var has been
`let`) writes a line shaped exactly `name = 1.234500e+00` -- this is more
robust across ngspice versions than `.measure`, which does not support the
plain `op` analysis type at all (verified against the locally installed
ngspice-47; `.measure op ...` errors with "unrecognized analysis type").
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[-+0-9.eE]+)\s*$")


def parse(log_text: str, names: list[str]) -> dict[str, float]:
    wanted = set(names)
    out: dict[str, float] = {}
    for line in log_text.splitlines():
        m = _LINE_RE.match(line.strip())
        if not m:
            continue
        name = m.group("name")
        if name in wanted and name not in out:
            try:
                out[name] = float(m.group("value"))
            except ValueError:
                continue
    return out


def missing(parsed: dict[str, float], names: list[str]) -> list[str]:
    return [n for n in names if n not in parsed]

"""Parse `let <name> = <expr>` / `print <name>` output from an ngspice batch
log into a {name: float} dict.

ngspice's `print <var>` (inside a .control block, after the var has been
`let`) writes a line shaped exactly `name = 1.234500e+00` -- this is more
robust across ngspice versions than `.measure`, which does not support the
plain `op` analysis type at all (verified against the locally installed
ngspice-47; `.measure op ...` errors with "unrecognized analysis type").

`parse()` defaults to a right-anchored match (nothing may trail the value),
which is correct for the plain `.meas tran X find ...` / `print`-style lines
above but rejects ngspice's TRIG/TARG crossing-based `.meas` lines outright
(silently yielding no match, not an exception): those print extra
" targ=... trig=..." context on the SAME line as `name = value`. Pass
`anchored=False` for that shape (issue #229 -- previously duplicated as a
private `_parse_trig_targ()` across three sim/ run scripts).
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[-+0-9.eE]+)\s*$")
_PREFIX_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[-+0-9.eE]+)")


def parse(log_text: str, names: list[str], *, anchored: bool = True) -> dict[str, float]:
    line_re = _LINE_RE if anchored else _PREFIX_LINE_RE
    wanted = set(names)
    out: dict[str, float] = {}
    for line in log_text.splitlines():
        m = line_re.match(line.strip())
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

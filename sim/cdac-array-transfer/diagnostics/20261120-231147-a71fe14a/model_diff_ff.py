#!/usr/bin/env python3
"""Issue #1013 model diff: transitive `.include` closure of the `.lib ff`
section of sky130.lib.spice, compared file-by-file between two open_pdks
installs (c6d73a3 fetched by volare into a throwaway root, f6eeac7 = the
pinned ~/.ciel install).

Usage: python3 model_diff_ff.py <old_root> <new_root>

Prints: entry-file hashes, closure sizes, only-old / only-new / differing
files, the active-line multiset comparison of the FET monolith vs the 22
split per-device files, and the added/removed/redefined parameters of any
differing rescap file. No simulation is run.
"""
from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

INCLUDE_RE = re.compile(
    r'^\s*\.include\s+"([^"]+)"|^\s*\.include\s+(\S+)', re.MULTILINE
)


def find_includes(text: str) -> list[str]:
    return [a or b for a, b in INCLUDE_RE.findall(text)]


def ff_closure(lib_spice: Path) -> list[Path]:
    """Files reachable from the `.lib ff` section via relative .include."""
    text = lib_spice.read_text(errors="replace")
    m = re.search(r"^\.lib ff\s*$(.*?)^\.endl ff\s*$", text, re.MULTILINE | re.DOTALL)
    if not m:
        raise RuntimeError(f"no .lib ff section in {lib_spice}")
    seen: dict[Path, None] = {}
    stack = [(lib_spice.parent / p) for p in find_includes(m.group(1))]
    while stack:
        path = stack.pop(0)
        f = path.resolve() if path.is_file() else None
        if f is None or f in seen:
            continue
        seen[f] = None
        for inc in find_includes(f.read_text(errors="replace")):
            stack.append(f.parent / inc)
    return list(seen)


def active_lines(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", ln.strip())
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("*")
    ]


def param_defs(text: str) -> dict[str, str]:
    out = {}
    for ln in text.splitlines():
        m = re.match(r"\+\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
        if m:
            out.setdefault(m.group(1), ln)
    return out


def main() -> int:
    # .resolve() through the variant dir too: volare roots expose sky130A as
    # a symlink into versions/<commit>/, and relative_to() needs real paths.
    old_root = (Path(sys.argv[1]) / "sky130A").resolve()
    new_root = (Path(sys.argv[2]) / "sky130A").resolve()
    for root in (old_root, new_root):
        stamp = (root / "SOURCES").read_text().splitlines()[0]
        lib = root / "libs.tech/combined/sky130.lib.spice"
        print(f"{root}: {stamp}; sky130.lib.spice sha256 "
              f"{hashlib.sha256(lib.read_bytes()).hexdigest()}")

    old = {
        str(p.relative_to(old_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ff_closure(old_root / "libs.tech/combined/sky130.lib.spice")
    }
    new = {
        str(p.relative_to(new_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ff_closure(new_root / "libs.tech/combined/sky130.lib.spice")
    }
    print(f"ff closure: old {len(old)} files, new {len(new)} files")
    print(f"only in old: {sorted(set(old) - set(new))}")
    print(f"only in new: {len(set(new) - set(old))} files:")
    for p in sorted(set(new) - set(old)):
        print(f"  {p}")
    differing = sorted(p for p in set(old) & set(new) if old[p] != new[p])
    print(f"differing same-path files: {differing}")

    # FET monolith vs split files: whitespace-normalized active-line multiset.
    old_active = active_lines(
        (old_root / "libs.tech/combined/continuous/models_fet.spice").read_text(errors="replace")
    )
    new_active = []
    for f in sorted((new_root / "libs.tech/combined/continuous/models_fet").glob("*.spice")):
        new_active.extend(active_lines(f.read_text(errors="replace")))
    co, cn = Counter(old_active), Counter(new_active)
    print(f"models_fet active lines: old {sum(co.values())}, new {sum(cn.values())}, "
          f"only-old {sum((co - cn).values())}, only-new {sum((cn - co).values())}")

    # rescap diff: purely additive parameter definitions?
    rescap = "libs.tech/combined/rescap/res_typical__cap_typical.spice"
    po, pn = param_defs((old_root / rescap).read_text()), param_defs((new_root / rescap).read_text())
    added = sorted(set(pn) - set(po), key=str.lower)
    removed = sorted(set(po) - set(pn))
    redefined = [p for p in set(po) & set(pn) if po[p] != pn[p]]
    rdl = [p for p in added if "rdl" in p and not p.startswith("c")]
    print(f"{rescap}: +{len(added)} params ({len(rdl)} RDL-res: {rdl}; "
          f"{len(added) - len(rdl)} interconnect-cap), removed {removed}, redefined {redefined}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

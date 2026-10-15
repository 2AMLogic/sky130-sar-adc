"""Resolve the sky130 PDK install the harness should run against.

Resolution order (env wins over the committed default, matching
sim/pdk.json's own convention and gf180-sar-adc's sim/harness/pdk.py):

  1. $PDK_ROOT / $PDK, if both set.
  2. sim/pdk.json's "default_pdk_root" (~/.ciel) / "variant" (sky130A); if
     that root has no variant directory, each of "fallback_pdk_roots"
     (~/.volare) in order. A fallback root is only ever a place to look: the
     open_pdks revision of whatever is found is still checked against the pin
     (see resolved_commit_verified()), so a leftover install at the old pin
     fails toolchain.check_env() instead of being used silently.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent


@dataclass
class PdkInfo:
    root: Path
    variant: str
    variant_dir: Path
    ngspice_lib: Path
    xschem_rc: Path
    open_pdks_commit_expected: str
    found: bool
    error: str = ""


def load_pdk_json() -> dict:
    with (SIM_DIR / "pdk.json").open() as f:
        return json.load(f)


def resolve() -> PdkInfo:
    cfg = load_pdk_json()
    root_env = os.environ.get("PDK_ROOT", "").strip()
    variant_env = os.environ.get("PDK", "").strip()

    variant = variant_env or cfg["variant"]
    if root_env:
        root = Path(root_env).expanduser()
    else:
        root = Path(cfg["default_pdk_root"]).expanduser()
        if not (root / variant).is_dir():
            for fallback in cfg.get("fallback_pdk_roots", []):
                candidate = Path(fallback).expanduser()
                if (candidate / variant).is_dir():
                    root = candidate
                    break
    variant_dir = root / variant
    ngspice_lib = variant_dir / cfg["ngspice_lib"]
    xschem_rc = variant_dir / cfg["xschem_pdk_rc"]

    if not variant_dir.is_dir():
        error = f"no PDK variant directory at {variant_dir}"
    elif not ngspice_lib.is_file():
        error = f"no ngspice model library at {ngspice_lib}"
    else:
        error = ""

    return PdkInfo(
        root=root,
        variant=variant,
        variant_dir=variant_dir,
        ngspice_lib=ngspice_lib,
        xschem_rc=xschem_rc,
        open_pdks_commit_expected=cfg["open_pdks_commit"],
        found=not error,
        error=error,
    )


_SOURCES_OPEN_PDKS_RE = re.compile(r"^open_pdks\s+([0-9a-f]{40})\s*$", re.MULTILINE)


def _commit_from_sources(variant_dir: Path) -> str | None:
    """The open_pdks revision recorded in the SOURCES file at the root of
    the variant tree (a line `open_pdks <40-hex>`), or None if the file is
    absent, unreadable, or has no such line. open_pdks writes SOURCES into
    the tree it installs, so this is independent of how the tree was fetched
    (ciel, volare, or a hand build).
    """
    try:
        text = (variant_dir / "SOURCES").read_text()
    except OSError:
        return None
    m = _SOURCES_OPEN_PDKS_RE.search(text)
    return m.group(1) if m else None


def _commit_from_path(variant_dir: Path) -> str | None:
    """The open_pdks commit volare encodes into the resolved variant
    symlink's path (.../sky130/versions/<commit>/sky130A), or None if
    variant_dir does not resolve through that shape.
    """
    try:
        resolved = variant_dir.resolve()
    except OSError:
        return None
    for part in resolved.parts:
        if len(part) == 40 and all(c in "0123456789abcdef" for c in part):
            return part
    return None


def _open_pdks_commit(variant_dir: Path) -> str | None:
    """The open_pdks revision of the tree at variant_dir: SOURCES first,
    the volare path layout as a fallback, None if neither yields one (a
    tree whose provenance this harness has no way to verify).
    """
    return _commit_from_sources(variant_dir) or _commit_from_path(variant_dir)


def resolved_commit_verified(info: PdkInfo) -> str | None:
    """The open_pdks commit actually installed at info.variant_dir, IFF its
    provenance can be verified (SOURCES file, else volare's path layout) --
    None otherwise.

    Callers that must fail closed on unverifiable provenance (e.g.
    toolchain.check_env()'s pin-drift gate) use this, not resolved_commit()
    below: resolved_commit() folds the unverifiable case into a *display*
    string (for evidence records, where "some string, honestly labeled" is
    the right answer), and that string must never be mistaken for a
    confirmed pin match -- see the fallback string's "(unverified -- ...)"
    suffix, which previously happened to `startswith()` the pin and so
    satisfied the drift gate for an install of unknown provenance.
    """
    return _open_pdks_commit(info.variant_dir)


def resolved_commit(info: PdkInfo) -> str:
    """Best-effort open_pdks commit actually installed at info.variant_dir,
    for DISPLAY in evidence records and summaries.

    Falls back to the expected pin annotated
    "(unverified -- no SOURCES file or volare layout)" so callers always get *some*
    string to record. This fallback is a display convenience only -- it
    must never be treated as proof the install is on pin; use
    resolved_commit_verified() for that decision.
    """
    commit = _open_pdks_commit(info.variant_dir)
    if commit is not None:
        return commit
    return info.open_pdks_commit_expected + " (unverified -- no SOURCES file or volare layout)"


def resolve_or_raise() -> PdkInfo:
    """resolve(), raising RuntimeError instead of returning an unfound
    PdkInfo. For callers (e.g. sim/comparator-decision/run.py's and
    layout/comparator/pex/regen_probe.py's driver functions) that treat an
    unresolvable PDK as a hard error rather than something they can report
    a CLI exit code for themselves -- see toolchain.check_env() / each
    script's own `--check-env` handling for the exit-code convention used
    where a graceful, non-raising report is wanted instead."""
    info = resolve()
    if not info.found:
        raise RuntimeError(f"PDK not resolvable: {info.error}")
    return info


def print_env(info: PdkInfo) -> str:
    """Eval-able shell export lines, for `source sim/env.sh`."""
    return f'export PDK_ROOT="{info.root}"\nexport PDK="{info.variant}"\n'

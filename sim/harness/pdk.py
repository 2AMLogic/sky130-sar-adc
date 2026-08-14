"""Resolve the sky130 PDK install the harness should run against.

Resolution order (env wins over the committed default, matching
sim/pdk.json's own convention and gf180-sar-adc's sim/harness/pdk.py):

  1. $PDK_ROOT / $PDK, if both set.
  2. sim/pdk.json's "default_pdk_root" (~/.volare) / "variant" (sky130A).
"""

from __future__ import annotations

import json
import os
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


def _load_pdk_json() -> dict:
    with (SIM_DIR / "pdk.json").open() as f:
        return json.load(f)


def resolve() -> PdkInfo:
    cfg = _load_pdk_json()
    root_env = os.environ.get("PDK_ROOT", "").strip()
    variant_env = os.environ.get("PDK", "").strip()

    root = Path(root_env).expanduser() if root_env else Path(cfg["default_pdk_root"]).expanduser()
    variant = variant_env or cfg["variant"]
    variant_dir = root / variant
    ngspice_lib = variant_dir / cfg["ngspice_lib"]
    xschem_rc = variant_dir / cfg["xschem_pdk_rc"]

    if not variant_dir.is_dir():
        return PdkInfo(
            root=root,
            variant=variant,
            variant_dir=variant_dir,
            ngspice_lib=ngspice_lib,
            xschem_rc=xschem_rc,
            open_pdks_commit_expected=cfg["open_pdks_commit"],
            found=False,
            error=f"no PDK variant directory at {variant_dir}",
        )
    if not ngspice_lib.is_file():
        return PdkInfo(
            root=root,
            variant=variant,
            variant_dir=variant_dir,
            ngspice_lib=ngspice_lib,
            xschem_rc=xschem_rc,
            open_pdks_commit_expected=cfg["open_pdks_commit"],
            found=False,
            error=f"no ngspice model library at {ngspice_lib}",
        )

    return PdkInfo(
        root=root,
        variant=variant,
        variant_dir=variant_dir,
        ngspice_lib=ngspice_lib,
        xschem_rc=xschem_rc,
        open_pdks_commit_expected=cfg["open_pdks_commit"],
        found=True,
    )


def _volare_commit_from_path(variant_dir: Path) -> str | None:
    """The open_pdks commit volare encodes into the resolved variant
    symlink's path (.../sky130/versions/<commit>/sky130A), or None if
    variant_dir does not resolve through that shape (e.g. a hand-installed
    or otherwise non-volare PDK, whose provenance this harness has no way
    to verify).
    """
    try:
        resolved = variant_dir.resolve()
    except OSError:
        return None
    for part in resolved.parts:
        if len(part) == 40 and all(c in "0123456789abcdef" for c in part):
            return part
    return None


def resolved_commit_verified(info: PdkInfo) -> str | None:
    """The open_pdks commit actually installed at info.variant_dir, IFF its
    provenance can be verified through volare's path layout -- None
    otherwise.

    Callers that must fail closed on unverifiable provenance (e.g.
    toolchain.check_env()'s pin-drift gate) use this, not resolved_commit()
    below: resolved_commit() folds the unverifiable case into a *display*
    string (for evidence records, where "some string, honestly labeled" is
    the right answer), and that string must never be mistaken for a
    confirmed pin match -- see the fallback string's "(unverified -- ...)"
    suffix, which previously happened to `startswith()` the pin and so
    satisfied the drift gate for an install of unknown provenance.
    """
    return _volare_commit_from_path(info.variant_dir)


def resolved_commit(info: PdkInfo) -> str:
    """Best-effort open_pdks commit actually installed at info.variant_dir,
    for DISPLAY in evidence records and summaries.

    Falls back to the expected pin annotated
    "(unverified -- non-volare layout)" so callers always get *some*
    string to record. This fallback is a display convenience only -- it
    must never be treated as proof the install is on pin; use
    resolved_commit_verified() for that decision.
    """
    commit = _volare_commit_from_path(info.variant_dir)
    if commit is not None:
        return commit
    return info.open_pdks_commit_expected + " (unverified -- non-volare layout)"


def print_env(info: PdkInfo) -> str:
    """Eval-able shell export lines, for `source sim/env.sh`."""
    return f'export PDK_ROOT="{info.root}"\nexport PDK="{info.variant}"\n'

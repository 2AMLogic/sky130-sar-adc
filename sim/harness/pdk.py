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


def resolved_commit(info: PdkInfo) -> str:
    """Best-effort open_pdks commit actually installed at info.variant_dir.

    volare stores the fetched commit in the path the variant symlink
    resolves to (.../sky130/versions/<commit>/sky130A); fall back to the
    expected pin if the symlink shape doesn't match (e.g. a non-volare
    install), so callers always get *some* string to record.
    """
    try:
        resolved = info.variant_dir.resolve()
        for part in resolved.parts:
            if len(part) == 40 and all(c in "0123456789abcdef" for c in part):
                return part
    except OSError:
        pass
    return info.open_pdks_commit_expected + " (unverified -- non-volare layout)"


def print_env(info: PdkInfo) -> str:
    """Eval-able shell export lines, for `source sim/env.sh`."""
    return f'export PDK_ROOT="{info.root}"\nexport PDK="{info.variant}"\n'

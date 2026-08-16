"""Evidence-record helpers shared by the PVT corner runner and the Monte
Carlo runner -- see sim/README.md for the append-only convention this
implements: every record pins PDK version, ngspice version, the DUT
netlist's SHA-256, the repo commit + dirty flag, and (for MC records) the
seed + sample count. A re-run never edits a prior record; it mints a new
<record-id> and, if it corrects or replaces a prior one, names it via
"Supersedes".
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GitInfo:
    commit: str
    branch: str
    dirty: bool


def git_info() -> GitInfo:
    def _run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    commit = _run("rev-parse", "HEAD")
    branch = _run("rev-parse", "--abbrev-ref", "HEAD")
    dirty = _run("status", "--porcelain") != ""
    return GitInfo(commit=commit, branch=branch, dirty=dirty)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(path.read_text())


def new_record_id() -> str:
    """<YYYYMMDD>-<HHMMSS>-<short-git-sha> -- gf180-sar-adc's sim/README.md
    <record-id> scheme, unchanged (see sim/README.md "Provenance")."""
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        sha = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        sha = "nogit"
    return f"{ts}-{sha}"


def environment_block(
    pdk_line: str,
    ngspice_line: str,
    netlist_sha256: str,
    extra: dict[str, str] | None = None,
) -> list[str]:
    git = git_info()
    lines = [
        "## Environment",
        "",
        f"- PDK: {pdk_line}",
        f"- ngspice: {ngspice_line}",
        f"- Harness: sim/harness {_harness_version()}",
        f"- git: `{git.commit}` on `{git.branch}`" + (" (dirty)" if git.dirty else " (clean)"),
        f"- DUT netlist sha256: `{netlist_sha256}`",
    ]
    if extra:
        for k, v in extra.items():
            lines.append(f"- {k}: {v}")
    return lines


def _harness_version() -> str:
    from . import __version__

    return __version__


def write_netlist_snapshot(experiment_dir: Path, record_id: str, netlist_fragment: Path) -> Path:
    """Snapshot the DUT netlist under <experiment_dir>/netlist-snapshots/ and
    set up <experiment_dir>/records/, returning the path the caller's
    evidence record should be written to. Shared by both write_evidence()
    implementations (PVT corner runner and Monte Carlo runner) -- see
    module docstring."""
    snapshots_dir = experiment_dir / "netlist-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / f"{record_id}.spice").write_text(netlist_fragment.read_text())

    records_dir = experiment_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    return records_dir / f"{record_id}.md"


def footer_lines(written_by: str, supersedes: str) -> list[str]:
    """The **Supersedes** + append-only boilerplate every evidence record
    ends with, parameterized by the calling script's path (e.g.
    `sim/run_corners.py` or `sim/monte_carlo.py`)."""
    return [
        f"- **Supersedes**: {supersedes or '(none)'}",
        "",
        (
            f"Written by `{written_by}`. Append-only: never edit or delete "
            "this file -- a re-run or correction mints a new record-id and "
            "points back here via **Supersedes** (see `sim/README.md`)."
        ),
        "",
    ]

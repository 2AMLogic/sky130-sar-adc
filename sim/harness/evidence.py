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
import json
import subprocess
import tempfile
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


def write_netlist_snapshot_text(experiment_dir: Path, record_id: str, netlist_text: str) -> Path:
    """Text-accepting sibling of write_netlist_snapshot(), for netlists that
    are generated text (e.g. a derived reduced sub-model deck) rather than a
    static on-disk fragment. Snapshot the netlist under
    <experiment_dir>/netlist-snapshots/ and set up <experiment_dir>/records/,
    returning the path the caller's evidence record should be written to."""
    snapshots_dir = experiment_dir / "netlist-snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / f"{record_id}.spice").write_text(netlist_text)

    records_dir = experiment_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    return records_dir / f"{record_id}.md"


def write_netlist_snapshot(experiment_dir: Path, record_id: str, netlist_fragment: Path) -> Path:
    """Snapshot the DUT netlist under <experiment_dir>/netlist-snapshots/ and
    set up <experiment_dir>/records/, returning the path the caller's
    evidence record should be written to. Shared by both write_evidence()
    implementations (PVT corner runner and Monte Carlo runner) -- see
    module docstring."""
    return write_netlist_snapshot_text(experiment_dir, record_id, netlist_fragment.read_text())


def run_klt_yield(measurements: list[dict], out_json_path: Path) -> dict | None:
    """Invoke `klt yield` against an already-built `measurements` list (each
    caller constructs its own `"name"`/`"unit"`/`"samples"`/`"limits"`
    entries -- see sim/cdac-array-transfer/run_mc.py and
    sim/enob-estimate/run_enob.py for the two current callers), writing the
    scratch sample file to a tempfile and the parsed report to
    `out_json_path`. Returns the parsed JSON report, or None if `klt` / its
    native yield extension is unavailable, its output isn't valid JSON, or
    the report itself carries an `"error"` key (recorded as an honest gap
    in the calling record rather than silently skipped).

    Extracted (issue #131) from the two byte-identical `_run_klt_yield`
    private helpers PR #130 introduced independently in both callers -- only
    this tempfile/subprocess/parse/cleanup plumbing was shared; each
    caller's own `measurements`-list construction stays at its call site."""
    doc = {"measurements": measurements}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(doc, f)
        sample_path = Path(f.name)
    try:
        proc = subprocess.run(
            ["klt", "yield", str(sample_path), "--format", "json"],
            capture_output=True, text=True, timeout=60,
        )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return None
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps(report, indent=2))
        if "error" in report:
            return None
        return report
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    finally:
        sample_path.unlink(missing_ok=True)


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

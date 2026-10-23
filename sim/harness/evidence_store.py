"""Write simulation evidence through the fleet artifact store (issue #717).

Evidence bytes (netlist snapshots, per-corner logs) do not land in git for new
runs. They go to the artifact store through `klt artifact put` (klayout-tools,
docs/cli/artifact.md) and git keeps a manifest,
`manifests/artifacts/<bench>-<run-id>.manifest.json`, plus the run's Markdown
record under `sim/<bench>/records/`. Evidence bytes are private and manifests
are public; every manifest `uri` is a logical `artifact:<key>` name.

Fail closed. Every failure raises StoreError: no broker configured, no `klt`
with the `artifact` verb, an unreachable or refusing broker, a put that fails
part-way, a manifest that disagrees with the bytes. Nothing is then written
under `manifests/` or `sim/`; the staged bytes stay in the git-ignored scratch
tree (`sim/.work/`). There is no fallback that commits the bytes instead.

The `artifact` verb is newer than the `klayout-tools==0.6.0` pin in
`layout/requirements.txt`, which is deliberately not moved (it would re-freeze
layout and signoff evidence). Run the writer with a separate client, e.g.
`uvx --from "klayout-tools @ git+https://github.com/2AMLogic/klayout-tools@7e3561f" ...`
or a venv inside your worktree, with that `klt` first on PATH. The broker URL
comes from $KLT_ARTIFACT_BROKER only; it is never written to the repo.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ENV_BROKER = "KLT_ARTIFACT_BROKER"
ENV_REPO = "KLT_ARTIFACT_REPO"
MANIFEST_DIR = Path("manifests") / "artifacts"
#: Scratch tree (git-ignored) where a stored run's bytes are staged.
WORK_DIR = Path("sim") / ".work"
#: klayout-tools commit that first carries the `artifact` verb in a usable form.
KLT_ARTIFACT_MIN_COMMIT = "7e3561f"
PROBE_TIMEOUT_S = 30
PUT_TIMEOUT_S = 900

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_URI_RE = re.compile(r"^artifact:(.+)$")
_RID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REMOTE_RE = re.compile(r"[:/]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class StoreError(RuntimeError):
    """Evidence could not be stored; nothing was committed (fail closed)."""


def manifest_path(repo_root: Path, bench: str, rid: str) -> Path:
    for part in (bench, rid):
        if not _RID_RE.match(part):
            raise ValueError(f"invalid bench or run id {part!r}")
    return repo_root / MANIFEST_DIR / f"{bench}-{rid}.manifest.json"


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _repo_name(repo_root: Path, env, run) -> str:
    repo = env.get(ENV_REPO)
    if not repo:
        try:
            p = run(["git", "-C", str(repo_root), "remote", "get-url", "origin"],
                    capture_output=True, text=True, timeout=30, check=False)
            remote = p.stdout.strip() if p.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            remote = ""
        m = _REMOTE_RE.search(remote)
        if m is None:
            raise StoreError(f"cannot tell which repo to store under: set ${ENV_REPO}")
        repo = f"{m.group(1)}/{m.group(2)}"
    return repo


def probe_broker(base: str, repo: str, timeout: float = PROBE_TIMEOUT_S) -> None:
    """One `stat` of the empty digest: proves the broker is reachable and admits
    this caller for `repo` before any simulation time is spent. 200 or 404
    passes; anything else raises."""
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname \
            or parts.username is not None or parts.password is not None \
            or parts.query or parts.fragment:
        raise StoreError(f"${ENV_BROKER} is not a plain http(s) base URL")
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = cls(parts.netloc, timeout=timeout)
    body = {"kind": "evidence", "repo": repo, "sha256": EMPTY_SHA256}
    try:
        conn.request("POST", parts.path.rstrip("/") + "/v1/stat",
                     body=json.dumps(body).encode(),
                     headers={"Content-Type": "application/json",
                              "Accept": "application/json"})
        resp = conn.getresponse()
        status, raw = resp.status, resp.read(64 << 10)
    except (OSError, http.client.HTTPException) as exc:
        raise StoreError(f"artifact broker unreachable ({type(exc).__name__})") from None
    finally:
        conn.close()
    if status in (200, 404):
        return
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    err = payload.get("error") if isinstance(payload, dict) else None
    raise StoreError(f"artifact broker refused this caller (HTTP {status}"
                     f"{': ' + err if isinstance(err, str) else ''})")


def preflight(repo_root: Path, *, klt: str = "klt", env=None,
              which=shutil.which, run=subprocess.run, probe=probe_broker) -> None:
    """Raise StoreError unless an evidence run could be stored. Call before
    spending simulation time."""
    env = os.environ if env is None else env
    base = env.get(ENV_BROKER)
    if not base:
        raise StoreError(f"no artifact broker configured (${ENV_BROKER} is unset)")
    exe = which(klt)
    if exe is None:
        raise StoreError(f"`{klt}` is not on PATH")
    try:
        p = run([exe, "artifact", "put", "--help"], capture_output=True, text=True,
                timeout=60, check=False)
        ok = p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    if not ok:
        raise StoreError(f"`{klt}` has no `artifact put` verb; use a separate "
                         f"klayout-tools client at or after {KLT_ARTIFACT_MIN_COMMIT} "
                         "(the layout pin is intentionally older)")
    probe(base, _repo_name(repo_root, env, run))


def _klt_error(stderr: str) -> str:
    try:
        err = json.loads(stderr)["error"]
        return f"{err.get('code', 'error')}: {err.get('message', '')}".strip()
    except (ValueError, KeyError, TypeError):
        lines = [ln for ln in stderr.strip().splitlines() if ln.strip()]
        return lines[-1][:300] if lines else "no diagnostic"


def _entry_problem(entry) -> str | None:
    if not isinstance(entry, dict):
        return "entry is not an object"
    if not (isinstance(entry.get("sha256"), str) and _SHA_RE.match(entry["sha256"])):
        return "bad sha256"
    if entry.get("kind") != "evidence":
        return "kind is not evidence"
    m = _URI_RE.match(entry.get("uri") or "")
    if m is None or m.group(1).rsplit("/", 1)[-1] != entry["sha256"]:
        return "uri is not artifact:<key> naming the sha256"
    if not isinstance(entry.get("producer"), dict):
        return "no producer"
    return None


def put_files(files: list[tuple[Path, str]], repo_root: Path, *,
              klt: str = "klt", run=subprocess.run) -> tuple[dict, list[str]]:
    """Store every (path, name); return (manifest, empty_names).

    One `klt artifact put --name NAME` per file, merged into a manifest in a
    private temporary directory (never in the repo). Zero-byte files cannot be
    stored; their names are returned so the record can list them. Every entry
    is cross-checked against a local re-hash. Any failure raises StoreError.
    """
    names = [n for _, n in files]
    if len(set(names)) != len(names):
        raise StoreError("two staged files map to the same evidence name")
    expected: dict[str, tuple[str, int]] = {}
    empty: list[str] = []
    with tempfile.TemporaryDirectory(prefix="evidence-manifest-") as tmp:
        tmp_manifest = os.path.join(tmp, "manifest.json")
        for path, name in files:
            sha, size = sha256_file(path)
            if size == 0:
                empty.append(name)
                continue
            expected[name] = (sha, size)
            cmd = [klt, "artifact", "put", str(path), "--name", name,
                   "--manifest", tmp_manifest, "--format", "json"]
            try:
                p = run(cmd, cwd=str(repo_root), capture_output=True, text=True,
                        timeout=PUT_TIMEOUT_S, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise StoreError(f"klt artifact put {name}: {type(exc).__name__}") from None
            if p.returncode != 0:
                raise StoreError(f"klt artifact put {name} failed "
                                 f"(exit {p.returncode}): {_klt_error(p.stderr)}")
        if not expected:
            raise StoreError("nothing to store: every staged file is empty")
        try:
            with open(tmp_manifest, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError) as exc:
            raise StoreError(f"klt wrote no readable manifest: {exc}") from None
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or manifest.get("schema_version") != 1:
        raise StoreError("klt manifest is not {schema_version: 1, entries: [...]}")
    by_name = {}
    for e in entries:
        problem = _entry_problem(e)
        if problem:
            raise StoreError(f"klt manifest entry invalid: {problem}")
        by_name[e.get("name")] = e
    if set(by_name) != set(expected):
        raise StoreError("klt manifest entries do not match the staged files")
    for name, (sha, size) in expected.items():
        if (by_name[name]["sha256"], by_name[name]["size"]) != (sha, size):
            raise StoreError(f"klt manifest entry for {name} does not match the "
                             "file's local sha256/size")
    manifest["entries"] = sorted(entries, key=lambda e: e["name"])
    return manifest, sorted(empty)


def install_manifest(manifest: dict, path: Path) -> None:
    """Create `path` exclusively: an existing manifest is never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
    except FileExistsError as exc:
        raise StoreError(f"{path.name} already exists; refusing to overwrite") from exc


def summary_section(manifest_rel: str, manifest: dict, empty: list[str]) -> str:
    """Markdown appended to a run's record: name, size and sha256 per object."""
    total = sum(e["size"] for e in manifest["entries"])
    lines = [
        "",
        "## Stored evidence",
        "",
        f"The raw bytes of this run are in the fleet artifact store, not in git. "
        f"Manifest: `{manifest_rel}` ({len(manifest['entries'])} objects, {total} B). "
        "Paths are the manifest `name`s. Check them with:",
        "",
        "```",
        f"klt artifact verify {manifest_rel}",
        f"klt artifact get {manifest_rel}#<name> -o <out>",
        "```",
        "",
        "| name | size (B) | sha256 |",
        "|---|---:|---|",
    ]
    for e in manifest["entries"]:
        lines.append(f"| `{e['name']}` | {e['size']} | `{e['sha256']}` |")
    for name in empty:
        lines.append(f"| `{name}` | 0 | `{EMPTY_SHA256}` (empty, not stored) |")
    return "\n".join(lines) + "\n"


def store_files(files: list[tuple[Path, str]], *, repo_root: Path, bench: str,
                rid: str, summary_text: str, summary_path: Path, put=None) -> Path:
    """Store `files`; write only their manifest and the run's record.

    Order matters for fail-closed: (1) refuse if the manifest or record
    already exists; (2) put every file; (3) install the manifest exclusively;
    (4) write the record exclusively with a "Stored evidence" section. A
    failure in (1)-(2) leaves nothing in the repo. Returns the manifest path.
    """
    mpath = manifest_path(repo_root, bench, rid)
    for p in (mpath, summary_path):
        if os.path.lexists(p):
            raise StoreError(f"{p.relative_to(repo_root)} already exists; refusing "
                             "to overwrite evidence")
    if not files:
        raise StoreError("nothing staged to store")
    manifest, empty = (put or put_files)(files, repo_root)
    mrel = mpath.relative_to(repo_root).as_posix()
    install_manifest(manifest, mpath)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(summary_path, "x", encoding="utf-8") as fh:
            fh.write(summary_text.rstrip("\n") + "\n" + summary_section(mrel, manifest, empty))
    except FileExistsError as exc:
        raise StoreError(f"{summary_path.name} appeared concurrently") from exc
    return mpath

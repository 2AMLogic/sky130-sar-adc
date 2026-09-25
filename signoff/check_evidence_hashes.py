#!/usr/bin/env python3
"""Signoff evidence freshness check -- re-hash every artifact the block manifest
cites, against the file on disk (issue #345).

    python3 signoff/check_evidence_hashes.py           # check (exit 1 on failure)
    python3 signoff/check_evidence_hashes.py --verbose # print every resolution

WHY THIS EXISTS, given that `klt signoff` already has a freshness gate.

`klt signoff --manifest` compares the manifest's pinned `content_hash` against
the cited envelope's own SELF-REPORTED `provenance.input.content_hash`. Both
sides of that comparison are statements *about* a revision; neither is the
revision. A manifest and an envelope can therefore go on agreeing with each
other indefinitely while the GDS or Markdown they describe is rewritten
underneath them -- the item stays `met`, with a pinned hash, and nothing
anywhere read the file.

klayout-tools#2196 surfaces that as `input_verified` on every met citation,
and for this block's citations it reports `null` on all of them:

  * the `generic` envelope backing item 8 -- by contract. A generic envelope's
    author chooses their own field names, so the grader cannot know that
    `source` is the artifact and must not guess.
  * the `klt drc` envelope backing item 3 -- incidentally. `klt drc` records
    `file` as the ABSOLUTE path it was invoked with, which here is a path
    inside the ephemeral agent worktree the flow ran in. It does not resolve
    from any other checkout, so there is nothing for the grader to re-hash.

Both gaps are generic tool gaps and are filed upstream as such. Until they are
closed, "every citation pins a content_hash that matches the committed
artifact" is this repo's obligation to enforce, not the grader's -- so it is
enforced here, mechanically, rather than asserted in prose that goes stale.

This check is deliberately HEADLESS: pure file reads and sha256, no `klt`, no
KLayout, no PDK, no network. It runs in `npm run check:ci` on every push, next
to the repo's other always-on citation gates, so it blocks a PR the same day
rather than waiting for the nightly.

WHAT IT CHECKS, per file-backed citation in signoff/block-manifest.json:

  1. The cited envelope exists and parses.
  2. If the manifest pins a `content_hash`, it equals the envelope's own
     recorded input hash. (This duplicates the grader's gate on purpose -- it
     is the half that still works when `klt` is not installed.)
  3. The artifact that hash DESCRIBES is found on disk and re-hashes to it.
     This is the half the grader cannot do.
  4. For an unpinned `lvs` citation -- item 4 here, because klt 0.5.0's `klt
     lvs` writes `provenance.input: null` and so offers no hash to pin -- the
     envelope's own `environment.layout_sha256` / `environment.reference_sha256`
     are re-derived from the committed netlists instead. An unpinnable citation
     is not an unverifiable one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "signoff" / "block-manifest.json"

# Which field of each envelope kind names the artifact its recorded input hash
# describes. Mirrors klayout-tools#2196's own kind table for the native kinds,
# and adds `generic`'s `source` -- which that table deliberately omits, since
# only the envelope's author knows it.
ARTIFACT_FIELD = {
    "drc": "file",
    "extract": "file",
    "lvs": "layout",
    "sim": "netlist",
    "pex": "layout",
    "generic": "source",
    # `klt erc` (item 11, issue #355). Like `drc`, it records the graded GDS as
    # `file` and its hash as `provenance.input.content_hash`. Unlike `drc`, the
    # envelope does NOT live beside the artifact it grades -- an ERC record is a
    # verdict about some OTHER record's GDS (layout/sar-adc-top/erc-reports/<a>/
    # grading layout/sar-adc-top/reports/<b>/sar_adc_top.gds), which is why
    # `resolve_artifact` below has to re-root the recorded absolute path rather
    # than rely on the basename-beside-the-envelope reading alone.
    "erc": "file",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def classify(envelope: dict) -> str:
    """Name the envelope kind, the same way `klt signoff` does.

    The literal `"kind": "generic"` self-declaration is checked AHEAD of every
    structural test, exactly as the grader checks it, so a generic envelope
    that happens to carry a colliding field can never be read as a native kind.
    """
    if envelope.get("kind") == "generic":
        return "generic"
    # `erc` is tested BEFORE `drc`: a `klt erc` envelope carries a `deck` block
    # too, and would otherwise be misread as a DRC report (whose `violations`
    # key it does not have, so today it would fall through to `unknown` -- but
    # relying on that absence is exactly the kind of accident that breaks on the
    # next envelope-schema change). The positive test is the same pair
    # `klt signoff` itself detects the kind by: a top-level `gates` list plus a
    # `gate_role` string.
    if isinstance(envelope.get("gates"), list) and "gate_role" in envelope:
        return "erc"
    if "violations" in envelope and "deck" in envelope:
        return "drc"
    if "mismatches" in envelope and "reference" in envelope:
        return "lvs"
    if "devices" in envelope and "nets" in envelope:
        return "extract"
    return "unknown"


def is_probeable_candidate(candidate: Path) -> bool:
    """True when `candidate` names a location inside THIS checkout.

    A candidate path is a guess about where a committed artifact might live, so
    it is only ever worth probing inside the repo. Anything that lands outside
    REPO_ROOT -- via an absolute recorded path, or a `..` that climbs out -- is
    by construction not a committed artifact, and probing it reaches into
    whatever unrelated thing happens to occupy that path on the current
    machine.

    Both sides of the comparison are resolved. `candidate.resolve()` was
    already following symlinks, but comparing it against an unresolved
    REPO_ROOT breaks whenever REPO_ROOT itself sits under a symlinked
    component (e.g. macOS `/var/folders/...` -> `/private/var/folders/...`,
    or a repo checked out through a symlinked path) -- a real candidate then
    resolves to a location "outside" REPO_ROOT purely because REPO_ROOT never
    got the same treatment, and every candidate is wrongly rejected (issue
    #368). Resolving REPO_ROOT here too closes that gap regardless of how it
    was constructed.
    """
    try:
        return candidate.resolve().is_relative_to(REPO_ROOT.resolve())
    except OSError:
        return False


def is_existing_file(candidate: Path) -> bool:
    """`Path.is_file()` that answers "no" instead of raising.

    `is_file()` swallows only the not-found family (ENOENT/ENOTDIR); every
    other OSError propagates. EACCES is the one that bites: when a parent
    directory of the candidate is not traversable by the current user, `stat()`
    raises PermissionError and a candidate that is merely un-probeable crashes
    the whole check. A candidate is a guess, so an unanswerable guess is "not
    found" -- never a traceback.
    """
    try:
        return candidate.is_file()
    except OSError:
        return False


def resolve_artifact(named: str, envelope_path: Path) -> Path | None:
    """Find the artifact an envelope names, trying each plausible reading.

    An envelope's recorded path was written relative to whatever directory the
    producing run used -- which, for this repo's layout flows, is an absolute
    path inside a since-deleted agent worktree. So the basename-beside-the-
    envelope reading is tried too: evidence committed next to its own inputs,
    which is exactly how every layout/*/reports/<id>/ directory is arranged.

    An ABSOLUTE recorded path is never a literal filesystem probe here. Both
    `REPO_ROOT / named` and `envelope_path.parent / named` collapse to the bare
    absolute path under pathlib's join semantics, so probing them asks about
    the producing machine's filesystem rather than this checkout's -- which
    answers wrong whether the path is absent (fine), present-but-unrelated (a
    stale sibling worktree, silently hashed instead of the committed file), or
    present-but-unreadable (PermissionError, crashing the check: exactly what
    CI hit on this repo's `klt drc` envelope, whose `file` is an absolute path
    into a foreign `.loom/worktrees/issue-326/` tree). Only the basename
    reading is meaningful for an absolute name, and it is tried unconditionally
    below.
    """
    named_path = Path(named)
    candidates = []
    if not named_path.is_absolute():
        candidates.append(REPO_ROOT / named_path)
        candidates.append(envelope_path.parent / named_path)
    candidates.append(envelope_path.parent / named_path.name)
    # RE-ROOTING an absolute recorded path (issue #355). The basename reading
    # above only finds artifacts committed BESIDE their envelope; a `klt erc`
    # record is a verdict about a *different* record's GDS, so its artifact is
    # never beside it. Each suffix of the recorded path is tried under
    # REPO_ROOT, longest first, so
    # `/some/foreign/worktree/layout/x/reports/<id>/top.gds` resolves to this
    # checkout's own `layout/x/reports/<id>/top.gds` -- and nothing else: this
    # is still not a literal probe of the producing machine's filesystem (the
    # objection in this function's docstring), because every candidate is
    # rebuilt under REPO_ROOT and filtered by `is_probeable_candidate`. Longest
    # suffix first so the most specific reading wins; a one-component suffix is
    # just the basename reading, already covered above.
    if named_path.is_absolute():
        parts = named_path.parts[1:]  # drop the filesystem root
        for start in range(len(parts) - 1):
            candidates.append(REPO_ROOT.joinpath(*parts[start:]))
    for candidate in candidates:
        if is_probeable_candidate(candidate) and is_existing_file(candidate):
            return candidate
    return None


def iter_citations(manifest: dict):
    """Yield (item_key, entry) for every evidence entry, flattening item 11's
    compound array form."""
    for key, entry in (manifest.get("evidence") or {}).items():
        if isinstance(entry, list):
            for index, part in enumerate(entry):
                yield f"{key}[{index}]", part
        else:
            yield key, entry


def check_citation(item_key: str, entry, failures: list[str], notes: list[str]) -> None:
    if isinstance(entry, str):
        entry = {"file": entry}
    if not isinstance(entry, dict):
        failures.append(f"item {item_key}: evidence entry is neither a path nor an object")
        return
    if "command" in entry:
        failures.append(
            f"item {item_key}: command-backed evidence is not supported by this check. "
            "Either add support here or state in signoff/README.md why that "
            "citation's freshness is verified some other way -- do not leave a "
            "citation silently unchecked."
        )
        return

    named_file = entry.get("file")
    if not isinstance(named_file, str):
        failures.append(f"item {item_key}: evidence entry has no 'file'")
        return

    envelope_path = REPO_ROOT / named_file
    if not envelope_path.is_file():
        failures.append(f"item {item_key}: cited envelope {named_file} does not exist")
        return
    try:
        envelope = json.loads(envelope_path.read_text())
    except json.JSONDecodeError as exc:
        failures.append(f"item {item_key}: cited envelope {named_file} is not valid JSON ({exc})")
        return

    kind = classify(envelope)
    recorded = (((envelope.get("provenance") or {}).get("input")) or {}).get("content_hash")
    pinned = entry.get("content_hash")

    # 2. manifest pin vs. the envelope's own recorded hash.
    if pinned is not None:
        if recorded is None:
            failures.append(
                f"item {item_key}: manifest pins content_hash but {named_file} "
                f"(kind={kind}) records no provenance.input.content_hash, so the "
                "pin can never be matched. Drop the pin and document the "
                "verification in signoff/README.md, or cite an envelope that "
                "carries one."
            )
            return
        if pinned != recorded:
            failures.append(
                f"item {item_key}: manifest pin {pinned} != {named_file}'s own "
                f"provenance.input.content_hash {recorded}"
            )
            return

    # 3. the envelope's recorded hash vs. the artifact it describes.
    if recorded is not None:
        field = ARTIFACT_FIELD.get(kind)
        if field is None:
            notes.append(f"item {item_key}: kind={kind} names no artifact field; input not re-hashed")
        else:
            named_artifact = envelope.get(field)
            if not isinstance(named_artifact, str):
                failures.append(
                    f"item {item_key}: {named_file} (kind={kind}) records an input hash "
                    f"but no '{field}' naming the artifact it describes"
                )
                return
            artifact = resolve_artifact(named_artifact, envelope_path)
            if artifact is None:
                failures.append(
                    f"item {item_key}: {named_file} names input '{named_artifact}' "
                    "which does not resolve to a committed file -- its recorded hash "
                    "describes nothing this repo contains"
                )
                return
            actual = sha256_file(artifact)
            if actual != recorded:
                failures.append(
                    f"item {item_key}: {artifact.relative_to(REPO_ROOT)} hashes to {actual}, "
                    f"but {named_file} claims {recorded}. The artifact changed under the "
                    "evidence: re-run the flow that mints it, then re-render "
                    "signoff/t1-report.json."
                )
                return
            notes.append(
                f"item {item_key}: {kind} input {artifact.relative_to(REPO_ROOT)} verified "
                f"({recorded[:23]}...)"
            )
    elif kind == "lvs":
        # 4. An lvs envelope with no provenance.input at all (klt 0.5.0). Its
        #    freshness lives in environment.{layout,reference}_sha256 instead;
        #    those are bare hex digests, not `sha256:`-prefixed.
        environment = envelope.get("environment") or {}
        for side, hash_field in (("layout", "layout_sha256"), ("reference", "reference_sha256")):
            recorded_hex = environment.get(hash_field)
            named_side = envelope.get(side)
            if not isinstance(recorded_hex, str) or not isinstance(named_side, str):
                failures.append(
                    f"item {item_key}: {named_file} carries neither provenance.input.content_hash "
                    f"nor environment.{hash_field} -- its freshness cannot be verified at all"
                )
                return
            artifact = resolve_artifact(named_side, envelope_path)
            if artifact is None:
                failures.append(
                    f"item {item_key}: {named_file} names {side} '{named_side}' which does "
                    "not resolve to a committed file"
                )
                return
            actual = sha256_file(artifact)
            if actual != "sha256:" + recorded_hex:
                failures.append(
                    f"item {item_key}: {artifact.relative_to(REPO_ROOT)} hashes to {actual}, "
                    f"but {named_file}'s environment.{hash_field} claims sha256:{recorded_hex}"
                )
                return
            notes.append(
                f"item {item_key}: lvs {side} {artifact.relative_to(REPO_ROOT)} verified "
                f"(sha256:{recorded_hex[:16]}...)"
            )
    else:
        notes.append(
            f"item {item_key}: {named_file} (kind={kind}) records no input hash; nothing to verify"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print every artifact resolution, not just failures",
    )
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"FAIL: {MANIFEST.relative_to(REPO_ROOT)} does not exist", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text())

    failures: list[str] = []
    notes: list[str] = []

    block = manifest.get("block")
    if not isinstance(block, str) or not block:
        failures.append(
            "block-manifest.json has no 'block' -- it is required, and is how this "
            "block's row is identified in the fleet roll-up (2AMLogic/2am#956)"
        )
    if manifest.get("kind") not in ("analog", "digital", "mixed-signal"):
        failures.append("block-manifest.json 'kind' must be analog, digital, or mixed-signal")

    for item_key, entry in iter_citations(manifest):
        check_citation(item_key, entry, failures, notes)

    if args.verbose:
        for note in notes:
            print(f"  ok   {note}")

    if failures:
        print("FAIL: signoff evidence freshness check", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    citation_count = sum(1 for _ in iter_citations(manifest))
    print(
        f"OK: signoff/block-manifest.json -- {citation_count} citation(s), "
        f"{len(notes)} artifact hash(es) re-derived from disk"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

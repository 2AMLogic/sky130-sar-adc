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
    if "violations" in envelope and "deck" in envelope:
        return "drc"
    if "mismatches" in envelope and "reference" in envelope:
        return "lvs"
    if "devices" in envelope and "nets" in envelope:
        return "extract"
    return "unknown"


def resolve_artifact(named: str, envelope_path: Path) -> Path | None:
    """Find the artifact an envelope names, trying each plausible reading.

    An envelope's recorded path was written relative to whatever directory the
    producing run used -- which, for this repo's layout flows, is an absolute
    path inside a since-deleted agent worktree. So the basename-beside-the-
    envelope reading is tried too: evidence committed next to its own inputs,
    which is exactly how every layout/*/reports/<id>/ directory is arranged.
    """
    candidates = [
        REPO_ROOT / named,
        envelope_path.parent / named,
        envelope_path.parent / Path(named).name,
    ]
    for candidate in candidates:
        if candidate.is_file():
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

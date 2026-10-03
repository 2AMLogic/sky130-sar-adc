#!/usr/bin/env python3
"""Provenance gate on this repo's *current* DRC evidence (issue #121).

WHY THIS EXISTS
---------------
Every "DRC-clean" claim this repo makes -- `layout/<flow>/README.md`'s verdict
tables, each flow's `reports/<stamp>/record.md`, and the Section 4 / Section 7
verdicts `docs/chipalooza/challenge-4-proposal.md` grades on them -- bottoms
out in a committed `drc*.json` payload whose `status` reads `clean`. Nothing
checked *which `klt drc` path produced that payload*, and the two paths are not
equally trustworthy:

  - `klt drc --deck sky130` runs klt's own curated rule table in-process.
  - `klt drc --engine klayout --deck-file <deck>.drc` shells out to a `klayout`
    binary running a PDK-native deck. klayout-tools#1941 (fixed by
    klayout-tools#1951, merged 2026-09-16T21:05:25Z, commit `3027079c`) showed
    that path treating a report file's mere presence as proof the deck ran:
    a deck that calls `report(...)` near the top and then aborts part-way
    through still leaves a well-formed report behind -- covering only the rules
    that ran before the abort -- and `klt` reported `status: "clean"`, exit 0.
    A false clean, indistinguishable from a real one by reading the payload's
    verdict alone.

That fix is merged but not in any published release (`klayout-tools`'s latest
tag/PyPI release is still `v0.5.0`; `layout/requirements.txt` pins
`klayout-tools==0.5.0`), so the affected behaviour is exactly what a `klt drc`
run in this repo does *today*. The defensible answer is not to wait for the
release but to state, mechanically, that no current DRC verdict rests on the
affected path -- which is what this gate does.

It is the always-on, PDK-free companion to `layout/bin/check-klt-pin-evidence.sh`
(issue #110): pure file reads, no PDK fetch, no `klt` install, no
`layout/.venv`, so it runs in CI's headless `checks` job (`npm run check:ci`)
rather than the PDK-gated `pdk-smoke` job that actually produces evidence. Like
that one it does not *produce* a verdict -- it refuses to let an untrustworthy
one become a flow's current evidence.

WHAT IT CHECKS
--------------
For every `layout/<flow>/reports/LATEST` pointer, in the report directory that
pointer resolves to, for every DRC payload (`drc*.json`, including the
per-block maps `drc.blocks.json` carries):

1. Curated-deck provenance -- the payload records no `engine` field and its
   `deck` is a curated deck name rather than a deck *file* (a value containing
   `/` or ending in `.drc`). Both are how `klt` stamps the
   `--engine klayout --deck-file` path, and that is the path klayout-tools#1941
   can false-clean.
2. No tolerated deck errors -- the payload carries no `engine_deck_errors`
   field. That field is klayout-tools#1951's own marker for a run invoked with
   `--allow-deck-errors`, i.e. one that knowingly accepted a partially-executed
   deck. Legitimate for a caller scoping around a known-unrunnable rule;
   never legitimate as the evidence behind an unqualified clean verdict.
3. Non-vacuous clean -- a payload reporting `status: "clean"` names at least one
   layer in `coverage.layers_checked`. A clean verdict over zero checked layers
   is the signature the false-clean payload actually has in this repo's own
   history (see below), and it is vacuous regardless of how it was produced.
   A `violations` payload is exempt: a report that found something is
   self-evidently the product of a deck that ran.

Finding no DRC payload at all is itself a failure, so a renamed directory or a
broken glob cannot turn this into a silent pass.

SCOPE: CURRENT EVIDENCE ONLY
----------------------------
Superseded report directories are deliberately out of scope. `layout/` evidence
is append-only and its supersession trail is kept on purpose -- this repo does
hold two payloads carrying the affected provenance, both in the superseded
`layout/sampling-frontend-wells/reports/20260825-231908-3e02f7e/` directory
(klt 0.3.0, `deck: "nwell_isolation.drc"`, `engine: "klayout"`, zero
`layers_checked` on each), from the n-well-isolation recipe that klt 0.4.0's
curated deck later made unnecessary. Exactly one of the two is a `clean`
verdict (`drc.wells.json`) -- the only shape klayout-tools#1941 can falsify.
Rewriting or deleting either would be falsifying the record; what matters is
that neither is what any verdict stands on today, and that the other one is
that same run's negative control (`drc.wells.fixture.json`, `violations`, 10
findings spread across `nwell.1`/`nwell.2a`/`difftap.8`/`difftap.10` -- all
four rules that deck file defines), which is direct in-repo evidence the deck
ran to completion rather than aborting early. This
gate holds the *current* evidence to the stronger standard, the same scoping
`docs/chipalooza/check_proposal_citations.py`'s check 3 uses ("a verdict must
stand on current evidence").

USAGE
-----
    python3 layout/bin/check_drc_evidence.py [--stats]

`--stats` prints the payloads inspected instead of checking them, which is what
to run when a failure message needs context. Exit status:

    0 - every current DRC payload has curated-deck provenance
    1 - one or more do not (each one listed on stdout)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# A JSON object is a DRC payload if it carries both of `klt drc`'s verdict
# fields. `drc_violation_fixture.json` (a shapes spec) and the `*.request.json`
# documents carry neither, so they are skipped without needing a name list.
VERDICT_FIELDS = ("status", "violation_count")

# How `klt` stamps a deck *file* rather than one of its own curated decks.
DECK_FILE_MARKERS = ("/", ".drc")


def _report_payloads(path: Path) -> Iterator[tuple[str, dict]]:
    """Every DRC payload in one JSON file, as `(locator, payload)`.

    A flow's `drc.json` is a single payload; `drc.blocks.json` is a map of
    per-block payloads; a future runner could emit a list. All three are walked
    so no shape silently escapes the gate.
    """
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    stack: list[tuple[str, object]] = [("", document)]
    while stack:
        locator, node = stack.pop()
        if isinstance(node, dict):
            if all(field in node for field in VERDICT_FIELDS):
                yield locator, node
                continue
            for key, value in node.items():
                stack.append((f"{locator}.{key}" if locator else key, value))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                stack.append((f"{locator}[{index}]" if locator else f"[{index}]", value))


def current_payloads() -> Iterator[tuple[str, Path, str, dict]]:
    """`(flow, path, locator, payload)` for every current DRC payload."""
    for pointer in sorted((REPO_ROOT / "layout").glob("*/reports/LATEST")):
        flow = pointer.parent.parent.name
        stamp = pointer.read_text().strip()
        if not stamp:
            continue
        report = pointer.parent / stamp
        for path in sorted(report.glob("drc*.json")):
            for locator, payload in _report_payloads(path):
                yield flow, path, locator, payload


def _where(path: Path, locator: str) -> str:
    relative = path.relative_to(REPO_ROOT)
    return f"{relative}:{locator}" if locator else str(relative)


def check_payload(flow: str, path: Path, locator: str, payload: dict) -> list[str]:
    """Checks 1 to 3 against one payload."""
    misses = []
    where = _where(path, locator)
    engine = payload.get("engine")
    deck = payload.get("deck")
    if engine is not None or (
        isinstance(deck, str) and any(marker in deck for marker in DECK_FILE_MARKERS)
    ):
        misses.append(
            f"{where}: `{flow}`'s current DRC evidence was produced by "
            f"`klt drc --engine klayout` against deck file `{deck}` -- that path "
            f"can report `status: \"clean\"` from a deck that aborted part-way "
            f"through (klayout-tools#1941, fixed by #1951 but not in any "
            f"published release). Re-run this flow with the curated "
            f"`--deck sky130` table and commit the fresh report."
        )
    if "engine_deck_errors" in payload:
        misses.append(
            f"{where}: `{flow}`'s current DRC evidence records "
            f"`engine_deck_errors` -- the run was invoked with "
            f"`--allow-deck-errors` and knowingly accepted a partially-executed "
            f"deck, so its verdict cannot support an unqualified DRC-clean claim."
        )
    if payload.get("status") == "clean":
        layers = payload.get("coverage", {}).get("layers_checked") or []
        if not layers:
            misses.append(
                f"{where}: `{flow}`'s current DRC evidence reports `clean` while "
                f"its own coverage block names no layer as checked -- a clean "
                f"verdict over zero checked layers is vacuous."
            )
    return misses


def check_tree() -> list[str]:
    """Every current DRC payload, plus the non-vacuity guard."""
    misses: list[str] = []
    inspected = 0
    for flow, path, locator, payload in current_payloads():
        inspected += 1
        misses.extend(check_payload(flow, path, locator, payload))
    if inspected == 0:
        misses.append(
            "no DRC payload found under any `layout/*/reports/LATEST` -- this "
            "gate must inspect real evidence, and an empty inspection is a "
            "failure rather than a pass."
        )
    return misses


def main(argv: list[str]) -> int:
    if "--stats" in argv:
        for flow, path, locator, payload in current_payloads():
            layers = payload.get("coverage", {}).get("layers_checked") or []
            print(
                f"{_where(path, locator)}: flow={flow} deck={payload.get('deck')!r} "
                f"engine={payload.get('engine')!r} status={payload.get('status')!r} "
                f"layers_checked={len(layers)}"
            )
        return 0

    misses = check_tree()
    if misses:
        print(f"FAIL: {len(misses)} DRC evidence provenance problem(s):")
        for miss in misses:
            print(f"  - {miss}")
        print()
        print(
            "Each payload above is a flow's CURRENT evidence (what its\n"
            "`reports/LATEST` resolves to), so a verdict stands on it today.\n"
            "Re-run the flow and commit fresh evidence -- do not delete the check."
        )
        return 1

    count = sum(1 for _ in current_payloads())
    print(
        f"OK: all {count} current DRC payload(s) under layout/*/reports/LATEST "
        f"come from the curated `--deck sky130` path"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# Gap to T1 (bronze) — where the verdict lives

**The verdict of record is `signoff/t1-report.json`**, rendered mechanically by
`klt signoff --manifest signoff/block-manifest.json` and re-graded by CI on
every push and pull request. Read it, or read `signoff/README.md`, which is the
claim written around it.

This file no longer carries an item table. It used to (a dated hand-read of the
checklist, 2026-08-16, against `main`@`d3fda4c`), and that is precisely why it
was replaced: a hand-maintained checkbox list goes stale the moment either the
evidence or the checklist moves, silently, with nothing to catch it. **Both
moved.** The evidence moved repeatedly — schematic, layout, corner and
Monte-Carlo campaigns all landed after that read — and the T1 checklist itself
grew an **eleventh item on 2026-09-17** (`klayout-tools#2025`, "Power delivery
(structural)"), which invalidated every prior hand-read in the fleet at a
stroke. A table that says "1/10 pass" cannot even be wrong about a checklist
that now has eleven items.

The superseded 2026-08-16 read is not archived into a second file — that would
just be a duplicate checklist to rot beside the first — but it is not lost
either: it is in this file's own git history (`git log --follow -p
docs/t1-gap.md`), which is where a citation of its wording (e.g. DR-003's
"no RTL/synthesis flow in-repo") resolves.

Two things also changed in the *shape* of the claim, and both are recorded in
the manifest rather than here:

- **This block's kind is `mixed-signal`, not `analog`.** The 2026-08-16 read
  called it analog, correctly for the tree it was written against — before
  `layout/sar-sequencer/` and `layout/seln-inverters/` existed. The block now
  has a real OpenROAD place-and-route flow for its standard-cell partition, so
  both columns of the per-kind items apply, one per partition, and the item
  table has 22 rows rather than 11.
- **The partition boundary is declared explicitly**, as the checklist requires
  of a mixed-signal claim — which nets and cells belong to which side, and where
  the boundary is crossed. It lives in the manifest's `partition_boundary` and
  is echoed verbatim into the report.

## Where to look

| Question | Answer |
|---|---|
| What is this block's T1 state right now? | `signoff/t1-report.json` (`tier`, `t1_met_count` / `t1_item_count`, per-row `status` + `reason`) |
| Why is each row the way it is, and what is *not* cited on purpose? | `signoff/README.md` |
| Which artifacts back the claim? | `signoff/block-manifest.json` — one evidence entry per cited item |
| What does the checklist actually say? | `klayout-tools/docs/design-evidence-tiers.md`, at the content hash the report pins (`source_doc_content_hash`); the pinned grader's wheel bundles a copy |
| Who is tracking the remaining gap? | Issue **#23**, the standing tracker, which points here and at the report |
| Item 11 specifically (`klt erc` supply evidence) | Issue **#344**; the committed run is `layout/sar-adc-top/erc-reports/20260923-143401-1ee4ba8/` (`erc.json` + `record.md`), and its one real finding — `VPWR`/`VGND` each splitting into two std-cell islands that never reach a top-level supply — is tracked as **#355** |

```bash
# The verdict, human-readable, from a checkout:
python3 -m venv .venv-signoff
.venv-signoff/bin/pip install -r signoff/requirements.txt
.venv-signoff/bin/klt signoff --manifest signoff/block-manifest.json \
  --format text --no-color
```

## What has *not* changed

These are properties of the claim, not of the checklist, and they still hold
exactly as they did when this file was a hand-read:

- **No grant is recorded in this repo.** `2AMLogic/product/everyblock/grants.md`
  is the authoritative ledger, and grants are recorded by the operator. A
  `tier: "T1"` line in `signoff/t1-report.json` would be a graded verdict, not a
  grant.
- **No spec row is relaxed to make a result pass.** A row that proves unmeetable
  is superseded by a new decision record and an operator ruling, never silently
  loosened.
- **Staleness is failure.** A report generated against an older netlist or
  layout revision than current `main` is stale, not passing. That rule is now
  enforced by two CI gates rather than asserted here — see `signoff/README.md`'s
  "Freshness: two gates, and what each one catches".
- **The harness is not the gap.** The sim harness and the `klt` layout flow are
  both demonstrated working with negative controls (`layout/trivial-cell/` and
  the two `sim/` self-test experiments). Those records are **harness proofs, not
  design claims** (`sim/README.md`), and none of them may be cited toward a T1
  item — which is also why none of them appears in the manifest.

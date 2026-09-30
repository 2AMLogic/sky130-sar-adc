# `klt erc` supply record `20260925-044420-f039594` — T1 item 11 (Power delivery, structural)

**Verdict: unchanged from the record it supersedes, on purpose.** The
supply-continuity half of item 11 PASSES; item 11 as a whole is still UNMET.
Both halves, stated up front so neither hides behind the other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0`.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed, see
  below). `klt signoff` renders that state `unmet` /
  `supply_spec_disclosed_tool_limitation`. A second, independent reason is that
  item 11's grading path consults item 4's LVS report first, which reports
  `mismatch` (klayout-tools#1878).

**Why this record exists at all: the spec's *prose* drifted a third time, not
its gate** (issue #364, Judge round after PR #380's SCOPE-citation fix). This
supersedes `erc-reports/20260925-011943-f981dc9/` on the **same GDS, same
graded content** — only `erc-supply-spec.json`'s `_comment` and
`ties_disclosure.reason` passages moved. The superseded record's own SCOPE
citation fix (repointing to `reports/20260924-234053-66dca3c/`) had left two
GDS-specific *shape counts* elsewhere in the same file still describing the
run that citation used to name (`…-b323061`, 10 fewer met3 shapes and one
fewer tap shape than the run actually graded):

1. the `met3` stackup comment's drawn-geometry count said "1418 shapes" —
   `b323061`'s met3 (70/20) count, not `66dca3c`'s (`klt layers --format json`,
   layer 70/datatype 20: `b323061` → 1418, `66dca3c` → **1428**);
2. `ties_disclosure.reason`'s tap count said "11 tap.drawing 65/44 shapes" —
   again `b323061`'s count, not `66dca3c`'s (layer 65/datatype 44: `b323061` →
   11, `66dca3c` → **12**).

Both counts now name the run SCOPE actually names. `ties_disclosure.reason` is
echoed **verbatim** into every `erc.json`, so the tap-count error was shipping
inside committed evidence; the met3 count lives only in a `_comment` and is
dropped from `erc.json` entirely, but it is prose read by anyone auditing the
stackup and was just as wrong.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260924-234053-66dca3c/sar_adc_top.gds` — **the same GDS** the superseded record graded |
| Layout content hash | `sha256:bbb9b5373d80e8bb6ca3a8f698700678686ca15f6df27fe8ef2b2a55a67ec223` (unchanged) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:429841c89ecc08652f12c0d7dacc18e6d21e0d2113b776aa11e5e97d6ed0943c`, moved from `sha256:9224444c9961508ee72ddb5369e300a1c16003d2b77c6a62c24308c4da11d756` (the superseded record's pin) |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |
| Gate nets checked | 210 (unchanged) |

## The non-tuning argument, re-checked

`run-erc.sh` computes a graded-content digest over exactly `stackup`, `vias`,
`nets[]` and `ties_disclosure.kind`, with every `_comment` (and any other
underscore-prefixed) key dropped at both levels — so a prose-only refresh
(including this one, a shape-count correction inside two `_comment`/`reason`
strings) cannot move it:

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

**Identical** to the superseded record's digest — both counts corrected here
live entirely inside comment/reason prose, never inside a graded field.

**A recursive field diff of the two reports' JSON finds exactly the same two
leaves a prose-only re-mint should move, and only those two:**

| Field | Superseded (`…-f981dc9`) | This record |
|---|---|---|
| `provenance.spec.content_hash` | `sha256:9224444c…` | `sha256:429841c8…` |
| `ties_disclosure.reason` | tap count "11" (stale, `b323061`'s count) | tap count "12" (`66dca3c`'s count) |

Everything else — `erc_findings` (empty), `erc_finding_count`, `erc_status`,
`status`, `gates` (all 210), `coverage`, `erc_coverage`, `provenance.input`,
`provenance.deck`, `provenance.devices` — is bit-identical, including every
per-supply island verdict, which is the claim "the gate did not move" actually
amounts to. The met3 stackup count fix (1418 → 1428) does not appear in this
diff at all — it lives in a `_comment` array, which `klt erc` does not echo
into its report — but it is corrected in the spec file itself.

## Everything about the layout itself is unchanged

This record grades the **same** GDS as `erc-reports/20260924-234116-66dca3c/`,
byte-identical by content hash, so that record's own analysis of the ground
mesh (issue #377 / `DR-013`), the per-supply island table, the antenna half,
and every cross-check ablation still describes the layout this record grades.
Nothing here repeats it; read that record for the layout-side evidence. This
record's only subject is the spec-prose refresh above.

## `erc.missing_tie`: not computed (absence of evidence, not evidence of absence)

Unchanged from every superseded record. No `ties[]` is declared, so
`erc.missing_tie` is **not computed** — it is not reported as a misleading zero:

```json
"ties_disclosure": { "kind": "tool_limitation", "reason": "..." }
"erc_coverage": { "inapplicable": [ { "id": "erc.missing_tie:[]",
                                      "reason": "ties_disclosed_tool_limitation" } ] }
```

The obstacle remains **klayout-tools#2169** — a `ties[]` declaration on a real
routed standard-cell design collapses into one electrical island and reports a
**false** `erc.supply_short`.

## Upstream friction

No new `klayout-tools` gap was filed from this increment. The three the
superseded record carries (klayout-tools#2169, #2401, #2457) are all unchanged
by a prose-only spec refresh.

## Follow-ups

- **`erc.missing_tie` stays ungraded** until klayout-tools#2169 is fixed.
- **The ground return is still unmeasured** — DR-012's second open item,
  tracked as **#378**, untouched by this change.
- **Staleness rule.** This record grades one specific GDS by content hash. A new
  `reports/<id>/` record from `run-flow.sh` makes this one stale, not wrong —
  re-run `run-erc.sh` to mint a fresh ERC record beside it.

# `klt erc` supply record `20260925-011943-f981dc9` — T1 item 11 (Power delivery, structural)

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

**Why this record exists at all: the spec's *prose* was re-minted a second
time, not its gate** (issue **#364**). This supersedes
`erc-reports/20260924-234116-66dca3c/` (issue #377's ground-mesh record) on the
**same GDS, same graded content** — only `erc-supply-spec.json`'s `_comment`
and `ties_disclosure.reason` passages moved, refreshing three passages that
still described the pre-#355/#362/#377 layout:

1. the `SCOPE.` block named `reports/20260919-050355-fb11617/sar_adc_top.gds`,
   several layout records ago, and now explains that `provenance.input`, not
   this sentence, is what pins which layout a given verdict is about;
2. the `VPWR` `nets[]` comment said the rail was "KNOWN to come back as more
   than one island" — false since issue #355 tied the two std-cell macros'
   met5 PDN straps into one rail;
3. `ties_disclosure.reason`'s stand-in evidence (c) quoted the pre-#355 split
   LVS correspondence (`VPWR<->VPWR_SEQ` / `VPWR$1<->VPWR_SELN`), where the
   record in hand has a single `VPB|VPWR` ↔ `VPWR` (pin).

`ties_disclosure.reason` is echoed **verbatim** into every `erc.json`, so a
factually wrong sentence was shipping inside committed evidence. A fourth,
smaller drift (the `met3` stackup comment's shape count) was fixed in the same
pass.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260924-234053-66dca3c/sar_adc_top.gds` — **the same GDS** the superseded record graded |
| Layout content hash | `sha256:bbb9b5373d80e8bb6ca3a8f698700678686ca15f6df27fe8ef2b2a55a67ec223` (unchanged) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:9224444c9961508ee72ddb5369e300a1c16003d2b77c6a62c24308c4da11d756`, **moved** from the `sha256:fd4f5a93160072689b6fbc52dcce01b7eab8b68c48e6dc2fb6632500aa929946` every run back through #377's supersedes chain pinned |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |
| Gate nets checked | 210 (unchanged) |

## The non-tuning argument, now computed by the tool instead of by hand

Every earlier prose-only re-mint (`20260924-230820-3e79547`, the record #364
first wrote before #377's mesh landed and this one now supersedes in turn) made
this case with a one-off `python3` field diff run by hand. `run-erc.sh` now
computes the equivalent check itself on every invocation — a graded-content
digest over exactly `stackup`, `vias`, `nets[]` and `ties_disclosure.kind`, with
every `_comment` (and any other underscore-prefixed) key dropped at both
levels:

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

That digest is **identical** to the one the same graded-field extraction
produces against `erc-supply-spec.json` as it stood before this refresh
(`origin/main`'s copy, pre-`_comment`/`ties_disclosure.reason` edit) — both
sides recomputed directly from the two spec revisions during this record's
preparation, same 64-hex-digit output. A whole-file hash cannot make that claim
across a prose edit; this one can, because it is computed *after* dropping the
prose.

**A recursive field diff of the two reports' JSON finds the same two leaves a
prose-only re-mint should move, and only those two:**

| Field | Superseded (`…-66dca3c`) | This record |
|---|---|---|
| `provenance.spec.content_hash` | `sha256:fd4f5a93…` | `sha256:9224444c…` |
| `ties_disclosure.reason` | pre-refresh stand-in (c) | refreshed stand-in (c) |

Everything else — `erc_findings` (empty), `erc_finding_count`, `erc_status`,
`status`, `gates` (all 210), `coverage`, `erc_coverage`, `provenance.input`,
`provenance.deck`, `provenance.devices` — is bit-identical, including every
per-supply island verdict, which is the claim "the gate did not move" actually
amounts to.

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

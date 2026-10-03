# `klt erc` supply record `20260924-190825-f3622fc` — T1 item 11 (Power delivery, structural)

**Verdict: the supply-continuity half of item 11 PASSES; item 11 as a whole is
still UNMET.** Both halves, stated up front so neither hides behind the other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) now resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0`. On the run this supersedes,
  `VPWR` and `VGND` each resolved to **two** disconnected islands that reached
  no top-level supply at all.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed, see
  below). `klt signoff` renders that state `unmet` /
  `supply_spec_disclosed_tool_limitation` — and does so for this block today:
  `signoff/t1-report.json`'s two item-11 rows are `unmet`. A second, independent
  reason is that item 11's grading path also consults item 4's LVS report, which
  reports `mismatch`.

This **supersedes** `erc-reports/20260923-143401-1ee4ba8/` (issue #344's first
run), which graded an older GDS. That record is not wrong and is not edited: it
graded the layout that existed, by content hash. Issue **#355** changed the
layout.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260924-190817-f3622fc/sar_adc_top.gds` |
| Layout content hash | `sha256:543efabf14d987eba951934941ce949114bfe2e06593bed7059079bebecf2df8` |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` (unchanged — `sha256:fd4f5a93…`, byte-identical to the run this supersedes) |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |

**The spec was not touched.** Its content hash is the same
`sha256:fd4f5a93160072689b6fbc52dcce01b7eab8b68c48e6dc2fb6632500aa929946` the
failing run pinned — the same four `nets[]`, the same stackup, the same vias.
The verdict moved because the *layout* moved, which is the only way a verdict is
allowed to move here (CLAUDE.md: "agents do not relax a spec line to make a
result pass"; #344's own instruction not to tune item 11's spec).

Both content hashes are asserted by `run-erc.sh` itself at the end of every run,
against the files on disk — a drifted hash aborts the run rather than producing
a report that merely looks pinned. The layout hash matches the same layout
record's own `drc.json`/`extract.json` `provenance.input.content_hash`, so all
three verdicts demonstrably grade the same bytes.

**New in this record: the recorded paths are repo-relative.** `klt erc` records
the input path it was invoked with, verbatim, as the envelope's own `file`. Up
to and including the superseded record that was an absolute path inside an
ephemeral agent worktree, which resolves from no other checkout — so a grader
could never re-derive the hash from the artifact, and (worse) *could* on the one
machine where the path still existed, making a `klt signoff` report rendered
there drift against CI's re-render of the same manifest. `run-erc.sh` and
`run-flow.sh` now invoke `klt` from the repo root with repo-relative paths, so
`file` resolves anywhere and `input_verified` is machine-independent.

## Per-supply verdict

`status` is **not** the item-11 verdict (an antenna or floating-gate finding in
the same report is a real defect but is not this item's subject —
klayout-tools#1994). The item's own pass conditions are per-supply:

| Supply | Islands | `erc.unconnected_net` | `erc.supply_short` | Continuity verdict |
|---|---:|---|---|---|
| `VDD` | 1 | none | none | **pass** |
| `GND` | 1 | none | none | **pass**, read narrowly — see below |
| `VPWR` | 1 | none | none | **pass** (was 2 islands) |
| `VGND` | 1 | none | none | **pass** (was 2 islands) |
| `erc.missing_tie` | — | — | — | **not computed** — see below, and it is why item 11 is not met |

`erc_coverage.checked` carries all four as
`erc.net_connectivity:["VDD"|"GND"|"VPWR"|"VGND"]`, so each is checked and
passing, not silently skipped. 210 gate nets are also checked
(`erc.floating_gate`, below).

## What changed, and what it rests on

Issue **#355**, implementing
[`DR-010`](../../../spec/decision-records/DR-010-digital-supply-domain-partition.md):
the digital domain stays independent of the analog `VDD`/`GND` domain and gets
its own top-level pins, and the two standard-cell macros — which are one logic
domain, not two — share one `VPWR` net and one `VGND` net.

Physically that is **one met5 rectangle per rail and no via at all**
(`build_layout.py`'s `digital_supply_rail()`). Both macros are placed at the
same `dy`, so `sar_sequencer`'s met5 PDN strap for a rail and one of
`seln_inverters`' straps for the same rail share an exact global y band; a
rectangle spanning that band is colinear with both and merges into one polygon,
carrying a top-level `VPWR`/`VGND` label on the stretch that lies west of both
macros. Measured directly in the graded stream (merged 72/20 region): the
`VPWR` rail is one polygon spanning x `15.000 … 172.208` µm and the `VGND` rail
one polygon spanning x `15.000 … 171.868` µm, where before there were two
disjoint polygons per rail.

## Cross-checks

Each of these was run against **this** GDS; none is assumed.

**1. The stackup is necessary, not padded — and met5/via4 are now load-bearing
for the digital rails specifically.** Ablating the spec makes supplies split
again, which is what shows each declared level carries real connectivity rather
than decorating the report:

| Spec | `VDD` | `GND` | `VPWR` | `VGND` |
|---|---:|---:|---:|---:|
| as committed | 1 | 1 | 1 | 1 |
| minus `met5` + `via4` | 1 | 1 | **2** | **2** |
| minus `via4` only | 1 | 1 | **3** | **3** |
| minus `via3` | **3** | 1 | **23** | **23** |

Read the middle two rows together. Without met5 the two macros' rails fall back
to exactly the two islands the superseded record reported — so the new met5
rectangle *is* what joins them, not some incidental overlap. Without via4 (met5
present) each rail splits into **three**: `sar_sequencer`'s met1 rails,
`seln_inverters`' met1 rails, and **one** met5 network spanning both macros.
That the met5 half is a single island is not inferred from the number — the same
via4 ablation against the **pre-#355** GDS
(`reports/20260923-131726-fa1e0af/sar_adc_top.gds`, this flow's previous
`reports/LATEST`) reports **four** islands per rail, exactly one more, which is
the second met5 group this rectangle absorbs:

| GDS, `via4` ablated | `VPWR` islands | `VGND` islands |
|---|---:|---:|
| `20260923-131726-fa1e0af` (pre-#355) | 4 | 4 |
| `20260924-190817-f3622fc` (this record's) | 3 | 3 |

**2. The verdict does not depend on `--deck sky130`.** Dropping the flag leaves
the supply verdict identical (0 findings). The flag matters for the MiM-cap
carve-out on signal nets, not for the supplies — the same conclusion the
superseded record reached from the failing side.

**3. `klt drc` on the same bytes is clean, including the met5 rules.** The
pinned 0.6.0 deck authors `met5.width.1` / `met5.space.1` / `met5.area.1`
(`reports/20260924-190817-f3622fc/drc.json`, `coverage.rules_checked`), and that
record reports `status: "clean"`, 0 violations. So the new geometry is graded
against sky130A's own `m5.1` (1.6 µm), `m5.2` (1.6 µm) and `m5.4` (4.0 µm²)
rather than argued to be legal.

**4. The LVS compare on the same record corroborates the merge and does not
regress.** `lvs.json`: 21/21/21 pins (two new top-level supply pins), 88
mismatches against the superseded run's 98, 803/869 devices matched against
794, DRC-clean throughout. The two rails now appear as one net each on both
sides instead of the `VPWR_SEQ`/`VPWR_SELN` pair the old reference encoded.

## Why `GND`'s pass must still be read narrowly

Unchanged from the superseded record, and it matters more now that the
continuity table is all-pass. `klt erc` is a purely geometric wire/via
connectivity model with no device recognition. This block's analog ground return
is partly the **p-substrate**, which `klt extract`'s sky130 deck synthesises as
one shared `vsubs` net regardless of drawn geometry and which no geometric model
can see. So `GND: 1 island` means *the drawn `GND` conductor is one island*, not
*every NMOS body reaches it*.

Two further limits of this row, stated so a passing table is not over-read:

- **One island is not the same as "reaches a pad."** `GND` has no top-level pin
  on this block at all (`.GLOBAL GND`, no port in `design/sar_adc_top.spice`'s
  own list; `cdac_array`'s fourth port is a literal `vsubs`). `klt erc` cannot
  see the difference. Filed as **#362**; `DR-010`'s "Open items" names it too.
  The digital rails are not in this position — `VPWR`/`VGND` each land on a
  drawn top-level pin, which is precisely what #355 added.
- The substrate half is what `erc.missing_tie` would have graded — and that
  check was not run.

## `erc.missing_tie`: not computed (absence of evidence, not evidence of absence)

Unchanged from the superseded record, and now the *only* thing standing between
this block and a met item 11 on the ERC side. No `ties[]` is declared, so
`erc.missing_tie` is **not computed** — it is not reported as a misleading zero.
The report says so in machine-readable form rather than only in prose:

```json
"ties_disclosure": { "kind": "tool_limitation", "reason": "..." }
"erc_coverage": { "inapplicable": [ { "id": "erc.missing_tie:[]",
                                      "reason": "ties_disclosed_tool_limitation" } ] }
```

`"kind": "tool_limitation"` (not `"unexpressible"`) is the accurate one here:
sky130 taps *are* nameable on this layout (`tap.drawing` 65/44 inside
`nwell.drawing` 64/20, wired to `li1` through `licon1` 66/44). The obstacle is
**klayout-tools#2169** — a `ties[]` declaration on a real routed standard-cell
design collapses into one electrical island and reports a **false**
`erc.supply_short`. Declaring `ties[]` would replace a stated gap with a
misleading finding, so it is left undeclared and disclosed.

**Well-tie evidence standing in for the ungraded check** (named so a reader can
go look, not asserted):

1. **Tap cells are instantiated.** `sky130_fd_sc_hd__tapvpwrvgnd_1` text on
   `text.drawing` 83/44, and 11 `tap.drawing` 65/44 shapes drawn.
2. **Body/tub nets are labelled.** `VPB` on `nwell.label` 64/5 and `VNB` on
   `pwell.label` 64/59.
3. **LVS net correspondence** (`reports/20260924-190817-f3622fc/lvs.json`)
   carries the supply nets. This stand-in is **stronger than it was** on the
   superseded record — the digital rails now correspond one-to-one (`VPWR` ↔
   `VPWR`, not the split `VPWR_SEQ`/`VPWR_SELN`) and 9 more devices match — and
   it is **still not a clean LVS**: that run's `status` is `mismatch` (88), and
   `GND`/`VGND` still do not appear in its `net_correspondence` at all. Item 4
   does not pass; stand-in (3) inherits that weakness.

## Antenna half (reported, not this item's subject)

210 gate nets, gate area computed as `poly ∩ diff` via
`stackup[0].active_layer` (klayout-tools#1979). Every gate reports
`antenna_verdict: "pass_partial"` and **zero** levels violate. `pass_partial`
rather than `pass` is expected, not a defect: sky130's published antenna table
covers li1/met1/met2 only, so the met3/met4/met5 levels this block declares are
`"unchecked"` — a coverage gap in the PDK's own rule table, recorded rather than
papered over. This is why the envelope's overall `status` is `clean_partial`
while `erc_status` is `clean`.

## Upstream friction: one prediction retired, one still open

The superseded record filed **klayout-tools#2400** (a `nets[]` entry matches
supplies by label *string*, so independent domains reusing a macro library's PG
pin names cannot be declared) and noted that item 11 would stay unsatisfiable
for this block *if* #355 resolved by keeping the two macros' rails independent
of each other. It did not: DR-010 makes them one domain with one net per rail,
so one label string names one net and the declaration is exact. **#2400 is not a
blocker for this block** — the gap it describes is real and stays filed, but
this design no longer stands behind it.

**klayout-tools#2401** (a mis-transcribed `stackup[].label_layer` is silent —
every declared net matches zero islands and reports as `erc.unconnected_net`,
indistinguishable from a real supply defect) is untouched by this run and still
open. Note that this record is a *clean* one, which is precisely the case where
#2401 would be least visible: the cross-check table above is what rules it out
here — a spec whose label layers were wrong could not produce islands that
*split* under ablation.

## Follow-ups

- **`erc.missing_tie` stays ungraded** until klayout-tools#2169 is fixed. That
  is the one item-11 sub-check this block still does not compute, and the
  reason a clean continuity table is not a met item.
- **`GND` has no top-level pin** — #362.
- **Staleness rule.** This record grades one specific GDS by content hash. A new
  `reports/<id>/` record from `run-flow.sh` makes this one stale, not wrong —
  re-run `run-erc.sh` to mint a fresh ERC record beside it.

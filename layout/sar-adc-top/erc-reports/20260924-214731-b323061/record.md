# `klt erc` supply record `20260924-214731-b323061` — T1 item 11 (Power delivery, structural)

**Verdict: the supply-continuity half of item 11 still PASSES, on a layout that
now has an analog ground pad; item 11 as a whole is still UNMET.** Both halves,
stated up front so neither hides behind the other:

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

**What this record adds over the one it supersedes is not a moved verdict — it
is a moved meaning of one row.** On
`erc-reports/20260924-190825-f3622fc/`, `GND`'s "1 island" was a pass that had
to be read with an explicit warning attached: that record's own "Why `GND`'s
pass must still be read narrowly" section said, in as many words, that *one
island is not the same as "reaches a pad"* — `GND` had no top-level pin on this
block at all, and `klt erc` structurally cannot tell the difference. That gap
was filed as **#362**. Issue #362 closed it: `GND` is now a top-level port of
`sar_adc_top` and a drawn top-level pin label on conductor this flow's own
routing cell draws. The ERC number is unchanged (1 island, and it was always
going to be), which is exactly why the caveat had to be removed by *changing the
layout*, not by re-reading the report.

This **supersedes** `erc-reports/20260924-190825-f3622fc/` (issue #355), which
graded an older GDS. That record is not wrong and is not edited: it graded the
layout that existed, by content hash. Issue **#362** changed the layout.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260924-214710-b323061/sar_adc_top.gds` |
| Layout content hash | `sha256:bc712e3c1c427e782ca0bd50031982a1831bd0eef21bc7491a8fb7299a95ec85` |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` (unchanged — `sha256:fd4f5a93…`, byte-identical to both runs this supersedes) |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `clean_partial` / `clean` (exit 0) |
| `erc_finding_count` | 0 |

**The spec was not touched.** Its content hash is the same
`sha256:fd4f5a93160072689b6fbc52dcce01b7eab8b68c48e6dc2fb6632500aa929946` the
two earlier runs pinned — the same four `nets[]`, the same stackup, the same
vias. The layout moved; the gate did not. (Its prose `_comment` passages still
describe the #344-era run — disclosed, tracked as **#364**, untouched here for
exactly the reason this paragraph relies on.)

## Per-supply verdict

`status` is **not** the item-11 verdict (an antenna or floating-gate finding in
the same report is a real defect but is not this item's subject —
klayout-tools#1994). The item's own pass conditions are per-supply:

| Supply | Islands | `erc.unconnected_net` | `erc.supply_short` | Continuity verdict |
|---|---:|---|---|---|
| `VDD` | 1 | none | none | **pass** |
| `GND` | 1 | none | none | **pass** — and now on conductor that reaches a top-level pin, see below |
| `VPWR` | 1 | none | none | **pass** |
| `VGND` | 1 | none | none | **pass** |
| `erc.missing_tie` | — | — | — | **not computed** — see below, and it is why item 11 is not met |

`erc_coverage.checked` carries all four as
`erc.net_connectivity:["VDD"|"GND"|"VPWR"|"VGND"]`, so each is checked and
passing, not silently skipped. 210 gate nets are also checked
(`erc.floating_gate`, below).

## What changed, and what it rests on

Issue **#362**, implementing
[`DR-012`](../../../spec/decision-records/DR-012-analog-ground-pad.md): the
block presents a **drawn analog `GND` pad**, which is the p-substrate node's own
front-side terminal rather than a second node beside it.

Physically that is **one via riser plus one met4 stub**
(`build_layout.py`'s `analog_ground_pad()`): the riser walks `comparator`'s own
drawn `GND` met1 pin at global (101.5, 193.8) up to met4 without moving
laterally, and a 0.4 µm-wide met4 stub runs **south** from there to
y = 170.0 — out of `comparator`'s own footprint (bbox y0 = 176.3), into the open
channel above `sampling_frontend` (bbox y1 = 147.22) — where the top-level pin
label sits. South rather than north because `comparator`'s own `CLK` column
rises to met4 at x = 102.1, 0.6 µm from this pin's x, which two 0.4 µm met4
wires cannot share under `m4.2` (0.30 µm); running south puts the two columns'
y spans 4.1 µm apart so they never face each other.
`_check_analog_ground_pad()` asserts that, rather than leaving it to be
re-derived.

## Cross-checks

Each of these was run against **this** GDS; none is assumed.

**1. The pad is joined to `comparator`'s own `GND` through this module's via
riser — it is not a floating shape that happens to carry the label.** Ablating
the spec's `via3` (met3↔met4) splits `GND` into exactly **two** islands, which
is the whole point: the two pieces are `comparator`'s own met1/met2/met3 ground
and this module's new met4 stub. Run the identical ablation against the
**pre-#362** GDS and `GND` reports no finding at all, because there was no
second level to split off:

| GDS, `via3` ablated | `GND` islands | `VDD` | `VPWR` | `VGND` |
|---|---:|---:|---:|---:|
| `20260924-190817-f3622fc` (pre-#362) | 1 (no finding) | 3 | 23 | 23 |
| `20260924-214710-b323061` (this record's) | **2** | 3 | 23 | 23 |

Ablating `via2` gives the same `GND: 2` (the riser is a stack; cutting it
anywhere below met4 severs the same two pieces), and ablating `met4` from the
stackup entirely returns `GND` to one island with no finding — the stub simply
leaves the model. The other three supplies are unchanged across every row, so
the split is attributable to this change and to nothing else.

**2. The label is on the stub, and the extraction resolves it.**
`reports/20260924-214710-b323061/extract.json` records two `GND` label positions
on the `GND|VGND` net: `(101.5, 193.8)` — `comparator`'s own, inside that
macro — and `(101.5, 170.0)`, this flow's own, drawn in `SAR_ADC_TOP_ROUTE` and
therefore the one `--pin-source-cells` can promote. A label at a position with
no conductor under it would not have appeared here at all.

**3. `klt drc` on the same bytes is clean.**
`reports/20260924-214710-b323061/drc.json` reports `status: "clean"`, 0
violations, so the new riser and stub are graded against sky130A's own met1–met4
width/space/enclosure rules rather than argued to be legal. The minimum-area
rules the pinned deck still does not author (issue #326) were measured
separately with `docs/chipalooza/measure_metal_min_area.py`: **143 shapes below
threshold on this GDS, the same 143 as on the pre-#362 GDS** — the new met3 pad
(the riser's pass-through, drawn at `ISLAND_PAD_UM`) and the new met4 polygon
are both above their own thresholds, so this change adds none.

**4. The LVS compare on the same record does not regress.**
`reports/20260924-214710-b323061/lvs.json`: **88 mismatches, the same 88** as the
superseded record, in the same four categories (`device.unmatched` 66,
`net.merged` 11, `net.split` 10, `topology.flattened` 1), the same 803/869
devices matched and the same 411/443 nets matched. Pin counts move from 21/21/21
to **21/22/22** — reference 22 because `GND` became a port, layout still 21
because `GND` and `VGND` are one extracted net, `matched` 22 because that one
layout pin answers both reference ports. See DR-012 and the next section.

## Why `GND`'s pass must be read narrowly — the part that is still true

The caveat this record retires is the *pad* half. The rest of the superseded
record's warning stands unchanged, and matters more now that a pass can be
mistaken for completeness:

- **`klt erc` has no device recognition.** It is a purely geometric wire/via
  connectivity model. This block's analog ground return is partly the
  **p-substrate**, which `klt extract`'s sky130 deck synthesises as one shared
  `vsubs` net regardless of drawn geometry and which no geometric model can see.
  So `GND: 1 island` still means *the drawn `GND` conductor is one island*, not
  *every NMOS body reaches it*.
- **Two of the four analog blocks still draw no ground conductor at all.**
  `sampling_frontend` and `cdac_array` reach this node only through that
  substrate synthesis; the pad this record grades is built on `comparator`'s
  pin because it is the only drawn analog-ground terminal in the composition.
  DR-012 records that as its central open item, with the follow-up that would
  close it.
- **`GND` and `VGND` are one extracted net** (`GND|VGND`, 692 devices) while
  this ERC model reports them as two independent single islands. Both readings
  are correct about different things: they share no *drawn conductor* (what
  `klt erc` sees) and they share the *p-substrate* (what `klt extract`'s deck
  synthesises). Bulk sky130 offers no way to make them two nodes; DR-010's
  partition is of metal return paths and pads, which is what a die-level
  decision can control, and DR-012 says so explicitly rather than letting the
  clean ERC table imply isolation.
- The substrate half is what `erc.missing_tie` would have graded — and that
  check was not run.

## `erc.missing_tie`: not computed (absence of evidence, not evidence of absence)

Unchanged from both superseded records. No `ties[]` is declared, so
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
3. **LVS net correspondence**
   (`reports/20260924-214710-b323061/lvs.json`) carries the supply nets, and is
   **one step stronger than on the superseded record for this record's own
   subject**: `GND` is now a declared port on the reference side and the
   `GND|VGND` layout net answers it, where before `GND` existed on the reference
   side only as an internal node. It is **still not a clean LVS**: that run's
   `status` is `mismatch` (88). Item 4 does not pass; stand-in (3) inherits that
   weakness.

## Antenna half (reported, not this item's subject)

210 gate nets, gate area computed as `poly ∩ diff` via
`stackup[0].active_layer` (klayout-tools#1979). Every gate reports
`antenna_verdict: "pass_partial"` and **zero** levels violate. `pass_partial`
rather than `pass` is expected, not a defect: sky130's published antenna table
covers li1/met1/met2 only, so the met3/met4/met5 levels this block declares are
`"unchecked"` — a coverage gap in the PDK's own rule table, recorded rather than
papered over. This is why the envelope's overall `status` is `clean_partial`
while `erc_status` is `clean`.

Worth one sentence because this change adds met4 to a ground net: the new stub
carries no gate, so it changes no gate's antenna ratio, and the met4 level was
already `"unchecked"` for every one of the 210 gates before it existed.

## Upstream friction

One new gap filed (below); both gaps the superseded record carried are unchanged
by this run:

- **klayout-tools#2169** (`ties[]` on a routed standard-cell design produces a
  false `erc.supply_short`) is why `erc.missing_tie` stays ungraded, and is the
  one item-11 sub-check this block still does not compute.
- **klayout-tools#2401** (a mis-transcribed `stackup[].label_layer` is silent —
  every declared net matches zero islands and reports as `erc.unconnected_net`,
  indistinguishable from a real supply defect) is untouched and still open. This
  is a *clean* record, the case where #2401 would be least visible; the ablation
  table above is what rules it out here, since a spec whose label layers were
  wrong could not produce islands that *split* under ablation.

One gap **was** filed from this issue, generically:
**klayout-tools#2457** — `klt erc`'s supply model has no rule for *"does this
declared supply reach a top-level terminal"*, so a rail drawn entirely inside
one macro, bonding to nothing, reports `clean` with an island count of 1. It is
a missing capability rather than a defect: the tool reports honestly against the
rules it has, and which labels count as top-level ports is not inferable from
geometry alone (it needs a pin source named the way `klt extract`'s
`--pin-source-cells` / `--def-pins` already do). It is filed because the absence
is what let this block carry an unbondable analog ground under a passing supply
table for as long as it did — ruling that out by hand, per net, is exactly the
cross-reference an ERC gate exists to remove.

## Follow-ups

- **`erc.missing_tie` stays ungraded** until klayout-tools#2169 is fixed. That
  is the one item-11 sub-check this block still does not compute, and the reason
  a clean continuity table is not a met item.
- **`sampling_frontend` and `cdac_array` still draw no ground conductor.** The
  pad this record grades reaches them only through the substrate — DR-012's own
  open item.
- **Staleness rule.** This record grades one specific GDS by content hash. A new
  `reports/<id>/` record from `run-flow.sh` makes this one stale, not wrong —
  re-run `run-erc.sh` to mint a fresh ERC record beside it.

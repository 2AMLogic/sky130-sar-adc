# `klt erc` supply record `20261001-022622-455b772` — T1 item 11 (Power delivery, structural)

**First ERC record on the re-composed top level (issue #401).** The layout this
grades is the first that places the glue `design/sar_adc_top.spice` actually
specifies — `layout/top-glue/`'s 33 `sky130_fd_sc_hd` cells and
`layout/halflsb-offset/`'s 8 `sky130_fd_pr` primitives — instead of the
DR-008-superseded `layout/seln-inverters/` bank. Both halves of item 11, stated
up front so neither hides behind the other:

- **Passing:** all four of this block's drawn supplies (`VDD`, `GND`, `VPWR`,
  `VGND`) resolve to **exactly one** electrical island each, with no
  `erc.unconnected_net` and no `erc.supply_short` anywhere —
  `erc_status: "clean"`, `erc_finding_count: 0` — on geometry where each of the
  four now has at least one *new* consumer.
- **Still unmet:** item 11 also requires zero `erc.missing_tie` *from a tie the
  run actually checked*, and this spec declares no `ties[]` (disclosed,
  unchanged, see the spec's `ties_disclosure`). `klt signoff` renders that state
  `unmet` / `supply_spec_disclosed_tool_limitation`. A second, independent
  reason is that item 11's grading path consults item 4's LVS report first, which
  reports `mismatch` (klayout-tools#1878 — unchanged by #401 and not closed by
  it, see `reports/20261001-022205-455b772/record.md`).

## Why this record exists: every declared supply gained a consumer

It supersedes `erc-reports/20260926-184830-e1176e3/` (issue #465's 2 × 2 via
arrays in the decoupling ties). The layout moved far more than that hop did:
`bin/build_layout.py` now places six sub-blocks instead of five, routes 36 nets
through the digital channel instead of 19, and — the part that matters *here* —
extends all four declared supplies to DR-009's offset network:

| supply | what #401 added to its drawn conductor | what a wrong leg would have looked like |
|---|---|---|
| `VDD` | `halflsb_offset.VDD` — the body/source rail of DR-009's three `pfet_01v8` switches, reached down this net's own west corridor (−8.0) | `VDD` at 2+ islands, or a short onto the adjacent `GND` corridor track 8 µm away |
| `GND` | `halflsb_offset.GND` — a **fourth** member of issue #377's analog ground mesh, teeing onto the same `cdac_array` corridor conductor that block's own `VSS` tap uses | `GND` at 2+ islands; or, if it teed onto the wrong track, a short between the analog mesh and a digital rail |
| `VPWR` | `halflsb_offset.VPWR` — `XMoff_p_cmp`'s gate, held high so the matching dummy stays off. Tapped off the met5 rail with one via4 at x = 17.0, west of both standard-cell macros | `VPWR` at 2+ islands (via4 missed the rail), or a short onto `VGND`, whose own tap is 1.6 µm away in x |
| `VGND` | `halflsb_offset.VGND` — `XMoff_p_refp`'s gate, ditto, tapped at x = 18.6 | ditto, mirrored |

**That is precisely the kind of change that has to be re-graded here rather than
reasoned about.** Two of the four legs reach a declared supply through a *single*
via4 cut off a 1.6 µm met5 rail, and the two taps sit 1.6 µm apart in x on the
two nets it would be worst to short; the `GND` leg joins a mesh whose own
correctness is already only visible to this tool. `build_layout.py` asserts the
enclosure arithmetic itself (`_check_halflsb_rail_taps()`: `m5.3` on all four
sides of each via4, and both taps clear of every macro footprint), but an
assertion about rectangles is not a connectivity verdict — this is.

Neither failure appears: **0 findings, 4/4 supplies at one island**, 257 gate
nets checked (up from 210 — the 33 glue cells and 8 offset primitives bring their
own gates). That is the independent structural confirmation the DRC verdict
cannot give (`klt drc` grades shapes, not connectivity) and that this flow's LVS
verdict cannot give either, because it is a pre-existing `mismatch`.

Produced by `layout/sar-adc-top/bin/run-erc.sh`. This is a verdict *about* an
existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20261001-022205-455b772/sar_adc_top.gds` — **a new GDS**, the first composing `top_glue` + `halflsb_offset` |
| Layout content hash | `sha256:ea954d318110ee5d2a39da926857393f42d96d17582734a7b6930e5520ca3346`, moved from `sha256:fe38e3b58f6d4867e5239911c9a7fbf3b2107d7265b732f48c978e4b6387aa9e` (the superseded record's pin) |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` — `sha256:8b69c6a2fb03e1e7459899c3edf4daa6e953348d42c08d63332428ed4d79c554`, moved from `sha256:6638db431ac6d04ef60055f5fa5c24f1ef415aae91c9119ee050c024421fbde9` by a `_comment` edit only (see "The non-tuning argument") |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| PDK | sky130A (open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json`, from the repo root with **repo-relative** paths |
| `status` / `erc_status` | `violations` / `clean` (exit 0) — the envelope-level `status` carries the antenna arm's partial coverage, not a supply finding; `erc_status`/`erc_finding_count` are the supply verdict |
| `erc_finding_count` | 0 |
| Gate nets checked | 257 (was 210) |

## The non-tuning argument

The spec's whole-file hash **did** move this time, and the graded-content digest
`run-erc.sh` computes over `stackup`, `vias`, `nets[]` and
`ties_disclosure.kind` **did not**:

```
run-erc.sh: graded-spec subset sha256=7f48fd89387b64b24c379baff04e6ef38361610240eac2c2d0adb8470584d982
```

Identical to the superseded record's digest and to all three of its
predecessors'. The whole-file difference is one `_comment` entry: that array
described the `seln_inverters` macro's own met5 strap x-range as the landmark the
digital rails are carried past, and #401 retired that macro — so the sentence was
corrected to name the digital standard-cell macro generically and to say
explicitly that its quoted x figures describe the run that comment names, not the
current one. **Nothing the gate reads changed**, which is exactly why
`run-erc.sh` computes a digest over a subset rather than over the whole file: a
spec whose prose can be corrected without re-opening the question it asks is a
spec whose question is stable.

So this is the same gate, unchanged, applied to a materially different layout.
The four supplies below are exactly the four this spec has always declared: #401
adds new CONDUCTOR on existing supplies, so item 11's question (does each
declared supply resolve to exactly one island?) is unchanged and its answer is
re-measured rather than re-scoped.

## Mesh ablation cross-check, re-run on the new geometry

`ground-mesh-ablation.json` in this record is a fresh run of
`bin/probe-ground-mesh.py` against the graded GDS (exit 0):

```
as_predicted: true          full_reproduces_record_gds: true
full_is_one_island: true    ablated_splits: true
controls_unmoved: true      controls_moved: []
third_leg_as_predicted: true
```

It is re-run rather than inherited because #401 added a **fourth member** to the
mesh, and because the ablation's own prediction changes shape as a result:

- `full_reproduces_record_gds: true` — the un-ablated variant the probe composes
  reproduces the graded GDS byte for byte (`sha256:ea954d31…` on both sides), so
  the new leg is in the record *and* in the probe's control arm.
- `ablated_splits: true` at **3** islands, up from the superseded record's 2 —
  and the new one is the finding, not a regression. The two already-known islands
  are unchanged (`sampling_frontend`'s own met1 ground, 13 shapes, bbox
  103.495–130.115 × 86.450–140.720 µm; `comparator`'s own met4 stub grown east to
  carry the decoupling pair, 10 shapes, bbox 100.200–227.900 × 150.000–197.900
  µm). The third, 5 shapes at bbox **122.851–139.451 × 65.200–78.980 µm**, is
  `halflsb_offset`'s own ground terminal: with the mesh cut it reaches nothing.
  **So the fourth leg is load-bearing by the same measurement the other three
  are** — an offset-network ground that the substrate alone joined would have
  left the ablated count at 2.
- `controls_unmoved: true` (`controls_moved: []`) — ablating the analog mesh
  moves `VDD`, `VPWR` and `VGND`'s island counts not at all, so DR-009's three
  new supply legs did not smuggle a path between the two domains.
- `third_leg_as_predicted: true` — the scratch-spec diagnostic still reports
  `VSS` and `GND` as one electrical net in the full variant and not in the
  ablated one, i.e. `cdac_array`'s differently-named terminal is still joined by
  metal rather than by assumption.

## What this record does NOT say

- **Not that the substrate half of `GND` is graded.** `klt erc` sees drawn
  conductor only. Every ground terminal here lands on the one extracted net
  `GND|VGND|VSS` — bulk sky130 offers no way to split it, per
  `spec/decision-records/DR-012-analog-ground-pad.md` — and a one-island verdict
  on `GND` still means "the drawn `GND` conductor is one island", not "every NMOS
  body reaches it".
- **Not that #401's LVS blocker moved.** It did not: `klt lvs` on the graded GDS
  still reports `mismatch`, for the one open reason it already had
  (klayout-tools#1878). What #401 changed is that the two sides of that compare
  are now independently derived, so the verdict will mean something when #1878
  clears — see that record's own "Composition parity and matched pairs" section.
- **Not that DR-009's dummy-load match is verified here.** `klt erc` is a
  connectivity model; a matched pair and a scattered one are the same verdict to
  it. The composition-level residual (6.5 % of drawn top-level conductor) is
  measured by `bin/build_layout.py` and reported in
  `reports/20261001-022205-455b772/composition.json`; the electrical check
  DR-009 asks for is a post-extraction re-run of
  `sim/full-conversion-transient/`, which no arm of this record performs.
- **Not that the decoupling meets DR-017's bounce target.** It does not, and
  DR-017's Decision §4 says so. Nothing in #401 touched the ties.

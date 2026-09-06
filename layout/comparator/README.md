# layout/comparator/ -- dynamic comparator physical layout (issue #101)

Physical layout for the dynamic (StrongARM-class) comparator sub-block,
drawn against `design/comparator.sch`/`.sym` (issue #54) -- see that file's
header for the topology and `sim/comparator-decision/testbench/
comparator_core.spice` for the xschem-derived device list this layout's
connectivity is checked against. Follows `layout/README.md`'s (and
`layout/trivial-cell/`'s / `layout/sar-sequencer/`'s) record convention.

**Status: DRC-clean and LVS-clean against DR-004 Amendment A's 11-device
topology (issue #180).** The layout was re-drawn to match the amended
schematic from issue #175 (the cross-coupled NMOS latch pair's sources moved
off hard-wired `GND` onto the input pair's own drain nodes `DIP`/`DIN`, with
a CLK-gated PMOS precharge device added on each -- 9 devices became 11): a
sixth `klt gen` block (`rstd`, the `M_RST_DIP`/`M_RST_DIN` precharge pair),
`DIP`/`DIN` added to the floorplan/routing with the same mirror-symmetry
treatment `OUTP`/`OUTN` already had, and the latch NMOS source terminals
re-routed off the `GND` rail onto `DIP`/`DIN`. The record referenced by
`reports/LATEST` (`reports/20260906-101004-1250ff4/`) carries all six of this
flow's verdicts, three positive and three negative:

| # | Verdict | Why it is here |
| --- | --- | --- |
| 1 | every `klt gen` matched device/pair block is DRC-clean *in isolation* | a composed-DRC failure can be attributed to the routing, not to a device |
| 2 | `klt drc` reports **clean** on the composed layout | the deliverable itself is rule-legal |
| 3 | `klt lvs` reports **match** against `reference.spice` | the drawn geometry is the schematic |
| 4 | `klt lvs` reports **mismatch** against `reference.broken-device.spice` | LVS notices a *device-parameter-only* corruption (one W changed, connectivity untouched) |
| 5 | `klt lvs` reports **mismatch** against `reference.broken-topology.spice` | LVS notices a *topology-only* corruption (one latch gate un-crossed, every parameter untouched) |
| 6 | `klt extract` reports **no** unbiased PMOS body net | the drawn n-well tie really biases every PMOS body to VDD, rather than the layout falling back to KLayout's synthesized proxy net |

Verdicts 4-5 are the falsifiability discipline `layout/trivial-cell/`
established for this repo (issue #2): a "match" verdict means nothing until
"mismatch" has been shown reachable on the same toolchain in the same run,
and the two corruption classes are independent on purpose -- a comparison
that only checked connectivity would pass verdict 4, and one that only
compared device parameters would pass verdict 5. Verdict 6 is this
sub-block's own addition: an LVS "match" against a reference that *declared*
the proxy body net would prove nothing about the ties actually being drawn,
so the body-tie claim gets its own assertion instead of riding on LVS.

## Which `klt` flow, and why

**Devices** come from `klt gen`'s `diff_pair`/`mos_array` generators -- the
family-1/family-4 "matched analog primitive" generators built for exactly this
kind of block. Not `klt place-and-route` (a digital standard-cell flow; this
is full-custom analog with a real matching judgement call, the opposite of
`layout/sar-sequencer/`'s case).

**Placement and every wire** come from `layout/comparator/bin/build_layout.py`,
emitted as a `klt draw` shape document and merged with the device blocks by
`klt gen-compose` used as a *placer only* (`placement.strategy: "explicit"`,
no `routing` block in the request).

That second half is a deliberate change of approach from this issue's first
increment (PR #108), which asked `klt gen-compose` to route and could not get
past a partial result. `klt gen-compose`'s own module docstring already says
its geometry is advisory -- "`klt drc` remains the rule-compliance authority
on the composed output, so a routed net (`routed: true`) is not a DRC-clean
guarantee". Measured against this block it is not merely advisory but
unusable as a signoff path:

- legs it reported `routed: true` landed `li1.space.1`/`met1.space.1`
  violations, while every input block was independently DRC-clean;
- a block carrying more than one same-block "self-net" -- which any
  `splits`-interleaved matched pair inherently does, since each device's own
  legs must tie together -- can only ever get one of them routed.

Both are filed **generically**, with no design content, at
[2AMLogic/klayout-tools#1386](https://github.com/2AMLogic/klayout-tools/issues/1386)
per `CLAUDE.md`'s friction protocol. `klt draw` is the documented escape
hatch for precisely this situation ("write a primitive GDSII/OASIS stream
from a JSON shape description" -- the deliberately-dumb write-side verb), and
routing against a router *this repo controls* is what makes a DRC-clean,
LVS-clean verdict reachable at all. The device geometry is still 100%
`klt gen`'s: nothing about the transistors is hand-drawn, and the matching
strategy below is unchanged from the first increment.

What makes the split safe: every `klt gen` block draws only
nwell/diff/poly/licon1/li1. **met1 and met2 are entirely unused by the device
blocks**, so the routing cell owns both planes outright and cannot short into
a block by running over it -- only a deliberately-placed `mcon` cut connects
a route to a block's li1 pad.

## Matching strategy (the judgement call this issue's acceptance criteria calls out)

Two halves, both deliberate: *device* matching, and *routing* symmetry.

### Devices

`design/comparator.sch` has five matched device pairs plus one unmatched
single device (the tail switch) -- DR-004 Amendment A (issue #175/#180) added
the fifth pair, the `M_RST_DIP`/`M_RST_DIN` precharge devices on `DIP`/`DIN`.
Effort is *not* spread evenly across them -- it is concentrated on the one
pair the issue's acceptance criteria and #29 actually track:

- **Input pair, M_INN/M_INP (`inpair` block) -- the matching-critical net.**
  `klt gen diff_pair --params '{"w_um": 2, "l_um": 0.5, "splits": 2, ...}'`:
  a true common-centroid cross-quad ("A B / B A") interleave of two W=2um legs
  per device, combining to the schematic's W=4um per device. This directly
  targets *gradient-induced* threshold/current mismatch -- a linear process
  gradient across the pair cancels to first order under common-centroid
  interleaving, which a plain side-by-side placement does not achieve.
- **Cross-coupled latch pairs (M_LATN_P/N, M_LATP_P/N), the reset pair
  (M_RST_P/N), and the DIP/DIN precharge pair (M_RST_DIP/M_RST_DIN, `rstd`).**
  Symmetric by schematic role (each pair is interchangeable under the
  OUTP<->OUTN / DIP<->DIN swap) but not the static input-offset net #29
  tracks -- these affect regeneration/precharge symmetry or speed, a
  second-order offset contributor, not the primary one. `splits: 1`: plain
  A/B placement, adjacent, identical orientation, one instance per device at
  its full schematic width. Proportionate effort: real, deliberate symmetry
  without spending the interleaved-leg complexity budget where the
  acceptance criteria doesn't ask for it. `rstd` is sized W=4um per device
  (not W=16um like the existing `rst` block) -- "same class" means the same
  generator/`splits` treatment, not the same width; see
  `reference.spice`/`comparator_core.spice` for the amended sizing.
- **Tail switch, M_TAIL (`tail` block).** A single device, no matching
  partner -- `klt gen mos_array` 1x1, reusing the same validated unit-device
  primitive (contact/landing-pad geometry) every other block already uses.

`layout/comparator/bin/gen_blocks.py`'s own module docstring carries this
writeup next to the actual generator params, so the rationale and the code it
explains never drift apart.

### Floorplan and routing

Device matching alone does not fix a dynamic comparator's offset. Its
decision is a *race* between OUTP and OUTN, so unequal wire capacitance on
the two output nodes biases that race exactly the way a device Vth mismatch
would. Post-#180, the same is true of `DIP`/`DIN`: the input pair's own
drain nodes and the latch NMOS sources land there, so unequal `DIP`/`DIN`
wire capacitance biases the decision the same way. Two things address it:

- **A mirror-symmetric floorplan.** Every `diff_pair` block's y origin is
  chosen so its Q1/Q2 boundary lands on one shared horizontal axis
  (`Y_AXIS`): the OUTP-side device of every pair below it, the OUTN-side
  device above it, tail switch and cross-quad centred on it. `rstd` (the
  DIP/DIN precharge pair) follows the same rule -- it reuses `latn`'s own
  anchor, since a W=4um `diff_pair`'s port geometry is identical regardless
  of flavor (only the pfet n-well margin changes the bbox, not the active
  area).
- **Mirror-matched routing.** Each negative-half branch is routed on the
  mirror image (`2*Y_AXIS - y`) of its positive-half counterpart's own
  y-track wherever that track is free, rather than on whatever the greedy
  track search reaches first (`build_layout.py`'s `MIRROR_PIN`) -- applied to
  `DIP`/`DIN` with the same rigor as `OUTP`/`OUTN`.

This is measured, not asserted: `reports/<record-id>/route.summary.json`
carries per-net met1/met2 area, via and contact counts, and the resulting
OUTP/OUTN, VINN/VINP and DIP/DIN imbalance, and `record.md` tabulates them.
On the current record (`reports/20260906-101004-1250ff4/`) the mirror
preference yields **OUTP/OUTN 2.84%**, **VINN/VINP 15.54%**, and
**DIP/DIN 6.7%** wire-area imbalance.

Two honest limits on any of these numbers, both discussed at length by the
real `klt pex` parasitic extraction issue #112 ran against the pre-#180
geometry (`layout/comparator/pex/`,
`reports/20260825-151036-aaf3010/record.md`):

- Wire *area* is a proxy for wire capacitance, not a parasitic extraction.
  On the pre-#180 geometry the real extraction restated the OUTP/OUTN and
  VINN/VINP imbalances in farads and found them smaller than the area proxy
  claimed (same qualitative ranking, smaller magnitude either way).
- The residual VINN/VINP imbalance is real and structural rather than a
  router failure: the cross-quad's upper-row gate pads put VINN's pad in
  the right column and VINP's in the left, while their trunks are on
  opposite sides, so the two wires must cross -- one above the pads, one
  below -- and cannot share a track. `klt gen`'s unit device also places both
  halves' gate pads on the same side (above their own diffusion), so gate
  pads are related by translation, not reflection, and the mirror preference
  is deliberately not applied to them.

`layout/comparator/pex/` has been re-run against the post-#180 geometry
(`reports/20260906-101231-1250ff4/record.md`): it restates OUTP/OUTN in
farads (1.964% total-capacitance imbalance) and VINN/VINP (5.977%), both
smaller than the area proxy's numbers, same ranking as before. **Its AC3/AC4
"is the routing-driven offset material" conclusion is currently UNCONFIRMED**
for this topology, though -- see `layout/comparator/pex/README.md`'s status
note and issue #187: the extracted-side leg's pick-off measurements look
suspect (a sign-flipped gain vs. the schematic side), most likely because the
fixed pick-off timing `pex/testbench.spice` uses was calibrated against the
pre-#175 topology's regeneration profile, not the amended one. No floorplan
change is warranted on the evidence in hand; whether the parasitic-driven
term is material is an open question issue #187 tracks, not a settled "not
material" the way the pre-#180 geometry's own PEX record could claim.

### Body ties

`gen_blocks.py` draws no guard ring on any block (`add_guard_ring: false`):
composing a *closed* guard/collector ring per block blocked `klt gen-compose`
from reaching almost any of that block's other ports, since every port not on
the ring sits inside a closed metal loop a route cannot legally cross.

Rather than leave every device's body on KLayout's synthesized `vsubs` proxy
net -- the "device.body_unverified" limitation
`layout/trivial-cell/README.md` documents -- `build_layout.py` draws the two
body-tie structures directly:

- a **p-substrate tie**: `tap` outside every n-well, contacted up to the GND
  net, which the sky130 extraction deck merges with every NMOS body terminal
  through its `connect_global(tap_substrate_outside, substrate_net)` wiring;
- an **n-well tie**: `tap` inside the well, contacted up to VDD, naming the
  well net (and so every PMOS body terminal) VDD.

The `latp`/`rst`/`rstd` blocks each draw their own local n-well; the routing
cell draws one enclosing n-well rectangle that merges them into a single well
and extends far enough right to hold `rstd` and the well tie. Verdict 6 above
asserts the result. `reference.spice` therefore declares real `B=GND` /
`B=VDD` body terminals rather than an aspiration.

## Running the flow

```sh
layout/bin/setup-venv.sh                 # once, or after bumping requirements.txt
source sim/env.sh                        # exports PDK_ROOT/PDK
layout/comparator/bin/run-flow.sh        # ~1 minute; exit 0 iff all six verdicts hold
cat layout/comparator/reports/$(cat layout/comparator/reports/LATEST)/record.md
```

Each run mints a new timestamped, append-only record under
`reports/<record-id>/` (same convention as `layout/trivial-cell/reports/` and
`layout/sar-sequencer/reports/`). The flow is deterministic -- no randomness
and no dict-ordering dependence in the router -- so a re-run from a clean
checkout at the same commit reproduces a byte-identical `comparator.gds`.

## Files

```
layout/comparator/
  reference.spice                     # LVS reference (schematic-correct target)
  reference.broken-device.spice       # negative control: device-parameter corruption
  reference.broken-topology.spice     # negative control: topology corruption
  bin/
    gen_blocks.py                     # the six klt gen invocations + matching-strategy rationale
    build_layout.py                   # floorplan + router: emits the klt draw and gen-compose requests
    run-flow.sh                       # gen -> per-block drc -> draw -> compose -> drc -> extract -> lvs -> record
    render-record.py                  # renders record.md, asserts the six verdicts
  reports/
    LATEST                            # record-id of the most recent run
    <record-id>/                      # append-only, one directory per run:
                                      #   <block>.gds/.json      the six klt gen blocks
                                      #   drc.blocks.json        per-block DRC
                                      #   draw.request.json      every wire, as klt draw input
                                      #   draw.json, route.gds   the drawn routing cell
                                      #   route.summary.json     per-net wiring + symmetry metrics
                                      #   compose.request.json, compose.json
                                      #   comparator.gds         THE DELIVERABLE
                                      #   drc.json, extract.json, comparator.extract.spice
                                      #   lvs.json + the two negative-control envelopes
                                      #   report.md, record.md
```

## Records are append-only

Same rule as `sim/` and `layout/trivial-cell/`: a re-run mints a new
`<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, UTC) and never edits an
existing report directory. `reports/20260825-131632-51cbdd4/` is the earlier,
honestly-PARTIAL record from this issue's first increment (PR #108);
`reports/20260825-135219-59f8e86/` and `reports/20260906-064104-eedd532/`
describe the pre-#180 (9-device) topology; all stay exactly as they were
minted. `reports/20260906-101004-1250ff4/` (`reports/LATEST`) is the current
record, against the amended 11-device topology. `record.md` stamps the `klt`
version, the KLayout engine version, the resolved PDK variant + open_pdks
commit, the DRC deck's content hash, and the repo commit with its dirty flag.

Like `layout/trivial-cell/`'s own bootstrap record, a record is minted from a
**dirty** working tree by construction -- the flow writes its own report files
into the repo before `record.md` is rendered. The record says so rather than
hiding it.

## Provenance

Pattern (per-block `klt gen`, timestamped append-only reports, positive +
negative verdicts asserted from JSON envelopes rather than exit codes)
follows `layout/README.md`'s and `layout/trivial-cell/`'s own conventions;
device sizing and topology are re-derived from `design/comparator.sch` /
`comparator_core.spice`, not copied from either sibling sub-block or any
external implementation -- clean-room, per `CLAUDE.md`.

Per `CLAUDE.md`'s friction protocol, any awkwardness, gap, or wrong behaviour
found in `klt` while doing layout work here is filed **generically** at
`2AMLogic/klayout-tools` -- tool gap, no design detail, since that tracker is
public and this repo is not.

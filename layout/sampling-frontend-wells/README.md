# layout/sampling-frontend-wells/ — isolated PMOS well/tap islands for the sampling front end (issue #122)

The sampling front end's PFETs do **not** all share one VDD-tied n-well.
`design/sampling_frontend.sch`'s decision record DR-004 requires a deliberate,
non-standard body tie: `Sa_p`/`Se_p` tie their PFET body to `BOOST_P` and
`Sa_n`/`Se_n` to `BOOST_N` — a bootstrapped node that rises *above* VDD during
sampling — while `Scp_p`/`Cmswp_p`/`Scp_n`/`Cmswp_n`/`Invp` tie body to VDD
normally. A VDD-tied body on `Sa`/`Se` forward-biases their drain/body junction
once BOOST exceeds VDD by a diode drop, injecting substrate current and
degrading the boosted voltage. That is load-bearing circuit behaviour, not a
layout nicety.

This directory is the **composition study that proves the requirement is
achievable in layout, and provably so** — the "Gap 2" that blocked
`#99` (the full sampling front end layout). It is deliberately *not* the whole
sub-block: it draws exactly the nine `sky130_fd_pr__pfet_01v8` instances of
`design/sampling_frontend.sch` and partitions them into three isolated n-well
islands. Every NFET in that schematic ties its body to the p-substrate, which
`klt extract` synthesizes as one shared net regardless of drawn geometry, so no
NFET can participate in — or falsify — a well-isolation claim. `#99` inherits
the recipe below; it does not have to re-derive it.

**Status: DRC-clean, LVS-clean, and every PFET body extracts on its own
island's tap net.** The record referenced by `reports/LATEST` carries all
eight of this flow's verdicts, six positive and two negative:

| # | Verdict | Why it is here |
| --- | --- | --- |
| 1 | every `klt gen` PFET block is DRC-clean *in isolation* | a composed-DRC failure can be attributed to the wells/routing, not to a device |
| 2 | `klt drc --deck sky130` reports **clean** on the composed layout | as of klt 0.4.0 this deck carries `nwell.width.1`/`nwell.space.1` directly, so this single verdict *is* the well-isolation claim — see "The DRC gap this recipe used to work around" below |
| 3 | that same curated deck reports **violations**, naming `nwell.space.1`, on a deliberately-illegal well-split fixture | verdict 2 means nothing until "violations" is shown reachable on the same deck in the same run |
| 4 | `klt precheck` passes | geometry hygiene; every pin label lands on drawn metal |
| 5 | `klt extract` reports **no** unbiased PMOS body net | no PMOS body fell back to KLayout's anonymous, DC-floating proxy net |
| 6 | `klt extract` reports **each** PFET's body on its own island's tap net — `Sa`/`Se` on `BOOST_P`/`BOOST_N`, the other five on `VDD` | **this is the question #122 asked**; verdict 5 alone would be satisfied by one VDD well over everything |
| 7 | `klt lvs` reports **match** against `reference.spice` | the drawn geometry is the schematic, body column included |
| 8a | `klt lvs` reports **mismatch** against `reference.broken-body-tie.spice` | LVS notices a *body-terminal-only* corruption (the four boosted bodies moved to VDD, nothing else changed) |
| 8b | `klt lvs` reports **mismatch** against `reference.broken-device.spice` | LVS notices a *device-parameter-only* corruption (one W changed, connectivity untouched) |

Verdicts 8a–8b are the falsifiability discipline `layout/trivial-cell/`
established for this repo (issue #2), with 8a specialised to this
sub-block's own claim. It is the important one: a layout that silently drew one
VDD-tied well over the whole PFET set would still be DRC-clean, would still
extract nine PFETs, would still have every source/gate/drain net right, and
would still report `unbiased_pmos_body_nets: []`. Verdict 8a is what makes
verdict 7 evidence rather than an artefact of a checker that ignores the body
column.

**History (issue #149):** this table used to carry eleven verdicts across
*two* DRC decks. klt 0.3.0's curated sky130 deck carried no n-well rules at
all, so a hand-written DRC-DSL deck (`drc/nwell_isolation.drc`, run through
`klt drc --engine klayout --deck-file`, which shells out to a standalone
`klayout` binary) carried the isolation claim, with the curated deck's
vacuous "clean" on the same illegal fixture recorded as evidence of the gap
itself (the old verdict 5). klt 0.4.0 added `nwell.width.1`/`nwell.space.1`
to the curated deck (2AMLogic/klayout-tools#1420), which **inverted** that
verdict — the curated deck no longer reports the illegal fixture clean, it
reports it as violations — so #149 retired the hand-written deck and its
`--engine klayout` stages (this repo's environment has no working `klayout`
binary to run them with anyway) and collapsed the old verdicts 2–5 into the
new verdicts 2–3 above.

## The recipe

Four parts, all required. Dropping any one yields a layout that can still pass
DRC while being electrically wrong. The authoritative version lives next to the
code in `bin/build_layout.py`'s module docstring ("THE RECIPE"), so the prose
and the geometry it describes cannot drift apart; this is the summary.

1. **Partition the PFETs by body net and make the partition the floorplan.**
   `bin/gen_blocks.py`'s `DEVICES` table carries a `domain` per device and is
   the single source of truth — `build_layout.py` reads it for both the well
   partition and the tap net, and `bin/render-record.py` re-derives the
   *expected* body net from it when asserting the extracted result. A domain
   must be a contiguous x range in the floorplan; that is what lets one
   rectangle per domain do the whole job.

2. **One n-well rectangle per domain, drawn by the composition, merging that
   domain's blocks' own wells and nothing else's.** `klt gen mos_array
   --params '{"flavor": "pfet"}'` draws a small local n-well around its own
   unit device; overlapping rectangles merge into one KLayout region, so a
   single drawn rectangle spanning one domain merges exactly that domain's
   device wells and extends far enough to hold a tap. Two domains' rectangles
   must clear `nwell.2a` (1.27 µm); this flow draws 1.60 µm and asserts it at
   build time (`_assert_well_isolation`) as well as in DRC.

3. **A tap inside each island, routed to that domain's own signal net.** A
   `tap` (65/44) shape inside the island, contacted up through licon1/li1 and
   then mcon/met1/via/met2 onto the *same* net the devices' source/drain
   terminals use — not a separate "well supply". `klt extract`'s sky130 deck
   splits `tap` by `nwell` containment and wires each tap to the well region
   containing it, so the well net — and therefore every PMOS body inside it —
   takes the tap's net name.

   **No `nwell.pin` (64/5) well label is drawn anywhere, deliberately.** A drawn
   well label would name the well even if the tap routing were broken, turning
   verdict 6 into a tautology. The name has to arrive through real
   connectivity or not at all.

4. **Verify the split against a deck that actually carries n-well rules** — see
   below.

### The DRC gap this recipe used to work around (closed by klt 0.4.0)

`klt drc --deck sky130`'s curated rule table, at klt 0.3.0, contained **no
n-well rules at all**: its rule ids covered poly/diff/li1/mcon/met1–met5/
via–via4/capm/capm2 and nothing on layer 64. A *deliberately* split well
therefore passed it vacuously on exactly the rules that govern the split. Two
n-well rectangles 0.5 µm apart — illegal, and physically one merged well on
silicon — came back `status: clean, violation_count: 0`.

`klt drc --engine klayout --pdk sky130A` did not close it either: it resolves
the PDK's own `sky130A.lydrc`, but that deck defaults its front-end-of-line
rule group off (`FEOL = false`) and klt's klayout engine at the 0.3.0 pin
passed only `-rd input=` / `-rd report=`, with no way to set the deck variables
that would switch FEOL on. The same fixture came back "clean" through that
path too, and because that engine reports an empty `coverage` block, nothing in
the envelope said a whole rule group was skipped.

**klt 0.4.0 closed the gap directly** (2AMLogic/klayout-tools#1420,
transcribed from sky130's own `nwell.1`/`nwell.2a`): the curated deck now
carries `nwell.width.1` and `nwell.space.1`. Measured directly, drawing
`drc/nwell_violation_fixture.json` (two 2×2 µm n-well islands 0.5 µm apart,
plus a 0.6 µm-wide n-well stripe) and running it through `klt drc --deck
sky130`:

```
status: violations, violation_count: 2,
rule_counts: {'nwell.space.1': 1, 'nwell.width.1': 1}
```

That is the negative control `run-flow.sh` now records directly (no second
deck, no standalone `klayout` binary) — see the verdict table above.

**What is still not covered**: `nwell.width.1`/`nwell.space.1` do not cover
sky130's `difftap.8`/`difftap.10` (minimum p+diff/n+tap enclosure by n-well).
This sub-block's old hand-written deck (`drc/nwell_isolation.drc`, retired by
#149) approximated those two rules by dropping their official `and(nsdm)`/
`and(psdm)` implant-layer scoping — an approximation that was exact for this
PFET-only cell but stated in that file's header as unsafe to copy into a
sibling sub-block with a p-substrate tap. klt 0.4.0 deliberately does not
transcribe difftap.8/difftap.10 into the curated deck either (they are
implant-scoped, and no `klt gen` generator in this repo's flows draws
`psdm`/`nsdm`), and this repo's environment has no working `klayout` binary
to check them any other way (`klayout -v` hangs indefinitely here). So this
flow currently checks n-well width/spacing only, not tap/diff enclosure by
n-well — a real, open gap, not one this issue closes.

This is not a general-purpose FEOL deck and must not be read as one:
`klt drc --deck sky130` remains the authority only for the rules it carries,
and it does not check poly/implant/density rules on this layout.

Findings filed **generically**, with no design content, at
`2AMLogic/klayout-tools` per `CLAUDE.md`'s friction protocol:

- [klayout-tools#1420](https://github.com/2AMLogic/klayout-tools/issues/1420) —
  the curated sky130 deck carried no well-layer rules (filed by this issue,
  since **closed** upstream by the klt 0.4.0 release measured above);
- [klayout-tools#1421](https://github.com/2AMLogic/klayout-tools/issues/1421) —
  no `klt gen` primitive for a named-net well/tap island isolated from a
  caller-specified set of other wells, i.e. the generator that would have made
  `bin/build_layout.py`'s hand-composition unnecessary (filed by this issue,
  since closed upstream; this flow still composes the island by hand via
  `klt draw`, unaffected either way);
- [klayout-tools#1302](https://github.com/2AMLogic/klayout-tools/issues/1302) —
  the klayout engine's deck-variable gap. Filed and closed upstream on
  2026-08-22; moot for this sub-block now that its `--engine klayout` stages
  are retired.

### Why not `klt gen guard_ring`

`guard_ring` with `add_well: true` draws a tap ring inside its own well and is
the closest existing primitive — but its well tie ties to whatever the caller
routes the ring to, so it does not by itself *isolate* a named-net island from
a caller-specified set of other wells, and a closed ring around a device blocks
routing to every port inside it (the finding
`layout/comparator/bin/gen_blocks.py`'s docstring already records). No `klt
gen` generator produces a named-net-isolated well island directly, so this flow
composes one through `klt draw`, the documented escape hatch for exactly that.

## Layout choices that are *not* claims

- **No matching claim.** These nine devices are functionally distinct switches,
  not matched pairs, so every block is a plain `mos_array` 1×1 (`dummy: 0`,
  `gate_contact: true`) — no `splits`, no common-centroid interleave, no
  dummies. Spending `layout/comparator/`'s matching machinery here would be
  effort spent on nothing, and would invite a matching claim this flow has no
  evidence for.
- **No area claim.** The floorplan is one left-to-right row with generous
  channels, chosen so the routing is trivially verifiable, not compact. `#99`
  should re-floorplan for area; only the *well partition* rule (parts 1–3
  above) is meant to survive into it.
- **No parasitic claim.** Wire lengths here are an artefact of the row
  floorplan. `BOOST_x` is a high-impedance boosted node whose parasitic loading
  matters (`sim/sampling-frontend/`'s own settling result depends on it) —
  that is a `klt pex` question for the real layout, in `#99`'s scope, exactly
  as `layout/comparator/pex/` did for the comparator.

## Running the flow

```sh
layout/bin/setup-venv.sh                            # once, or after bumping requirements.txt
source sim/env.sh                                   # exports PDK_ROOT/PDK
layout/sampling-frontend-wells/bin/run-flow.sh      # ~30 s; exit 0 iff all eight verdicts hold
cat layout/sampling-frontend-wells/reports/$(cat layout/sampling-frontend-wells/reports/LATEST)/record.md
```

No standalone `klayout` binary is needed (issue #149): every stage runs
through klt's headless `--engine curated` DRC, `klt extract`, and `klt lvs`
(`engine: "klayout"` in the LVS request means klt's bundled `klayout` *Python
package*, not a standalone binary on PATH).

Each run mints a new timestamped, append-only record under `reports/<record-id>/`
(same convention as `layout/trivial-cell/reports/` and
`layout/comparator/reports/`). The flow is deterministic — no randomness and no
dict-ordering dependence — so a re-run from a clean checkout at the same commit
reproduces a byte-identical `sampling_frontend_pwells.gds`.

## Files

```
layout/sampling-frontend-wells/
  reference.spice                     # LVS reference (schematic-correct target)
  reference.broken-body-tie.spice     # negative control: the four boosted bodies moved to VDD
  reference.broken-device.spice       # negative control: device-parameter corruption
  drc/
    nwell_violation_fixture.json      # negative control: an illegal n-well split, run through the curated deck directly
  bin/
    gen_blocks.py                     # the nine klt gen calls + the device/domain table (source of truth)
    build_layout.py                   # THE RECIPE: well partition, taps, floorplan, routing
    run-flow.sh                       # gen -> per-block drc -> draw -> compose -> drc x2 -> precheck -> extract -> lvs x3 -> record
    render-record.py                  # renders record.md, asserts the eight verdicts
  reports/
    LATEST                            # record-id of the most recent run
    <record-id>/                      # append-only, one directory per run:
                                      #   <block>.gds/.json          the nine klt gen blocks
                                      #   drc.blocks.json            per-block DRC
                                      #   draw.request.json          wells + taps + every wire, as klt draw input
                                      #   wells.summary.json         the well partition, measured
                                      #   draw.json, route.gds       the drawn well/routing cell
                                      #   compose.request.json, compose.json
                                      #   sampling_frontend_pwells.gds   THE DELIVERABLE
                                      #   drc.json                   curated deck, composed layout (n-well isolation verdict, as of klt 0.4.0)
                                      #   nwell_violation_fixture.json/.gds, draw.fixture.json
                                      #   drc.curated.fixture.json   curated deck, illegal-fixture negative control
                                      #   precheck.json
                                      #   extract.json, *.extract.spice
                                      #   lvs.json + the two negative-control envelopes
                                      #   report.md, record.md
```

## Records are append-only

Same rule as `sim/`, `layout/trivial-cell/` and `layout/comparator/`: a re-run
mints a new `<record-id>` (`<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, UTC) and
never edits an existing report directory. `record.md` stamps the `klt` version,
the KLayout engine version, the resolved PDK variant + open_pdks commit, the
curated DRC deck's content hash, and the repo commit with its dirty flag.

Like every other layout record in this repo, a record is minted from a **dirty**
working tree by construction — the flow writes its own report files into the
repo before `record.md` is rendered. The record says so rather than hiding it.

## Provenance

Pattern (per-block `klt gen`, `klt draw` for everything the generators do not
draw, `klt gen-compose` as a placer only, timestamped append-only reports,
positive + negative verdicts asserted from JSON envelopes rather than exit
codes) follows `layout/README.md`'s and `layout/comparator/`'s own conventions.
Device sizing, topology and the body-tie domains are re-derived from
`design/sampling_frontend.sch` / `sim/sampling-frontend/testbench/
sampling_frontend_dut.spice` and from DR-004's stated requirement — not copied
from a sibling sub-block or any external implementation. Clean-room, per
`CLAUDE.md`.

Per `CLAUDE.md`'s friction protocol, any awkwardness, gap, or wrong behaviour
found in `klt` while doing layout work here is filed **generically** at
`2AMLogic/klayout-tools` — tool gap, no design detail, since that tracker is
public and this repo is not.

# layout/top-glue/ — top-level standard-cell glue bank (issue #387)

Physical layout for the **33 `sky130_fd_sc_hd` instances
`design/sar_adc_top.spice` adds directly at the integration level**, inside no
sub-block: DR-008's decision-directed CDAC bottom-plate drive, DR-008's
readout recode, and DR-009's comparator-load-balance and half-LSB-enable
logic. None of #99 (sampling front end), #100 (CDAC array), #101 (comparator)
or #102 (SAR sequencer)'s own schematics instantiate these cells; they exist
only in the integration schematic issue #103 owns. That is why this directory
lives next to `layout/sar-sequencer/` rather than inside any of them.

## What is here

Census, re-derived from `design/sar_adc_top.spice` on every run by
`bin/check-schematic-parity.py` (and independently reported by `python3
docs/chipalooza/check_proposal_citations.py --stats`):

| Cell | × | What it is | Owner |
| --- | --- | --- | --- |
| `and2_1` | 18 | `SELn<i> = DOUT<i> AND DOUT9N`, `SELp<i> = DOUT9 AND DOUT<i>` | DR-008 |
| `xor2_1` | 9 | `ADCOUT<i> = DOUT<i> XOR DOUT9N` (read-only readout recode) | DR-008 |
| `inv_1` | 3 | `xinv_dout9n`, `xinv_halflsb`, `xinv_clkcap` | DR-008 / DR-009 / #264 |
| `mux2_1` | 1 | `xdum_mux_n` — matched dummy load on the comparator's `OUTN` | DR-009 |
| `xnor2_1` | 1 | `xdum_xnor_n` — the second half of that dummy load | DR-009 |
| `and2b_1` | 1 | `xand_halflsb`, `HALF_LSB_EN = BUSY AND NOT(PH_B9)` | DR-009 |

**33 instances, 6 cell types, 234 transistors.** `netlist/top_glue.v` carries
the per-group rationale and the positional→named pin translation for each
instance line.

## What is NOT here, and why

`design/sar_adc_top.spice`'s top level also adds **8 `sky130_fd_pr`
primitives** — DR-009's half-LSB quantizer-offset network (`Choff_n`/`Choff_p`,
two `cap_mim_m3_1`; `Moff_{n,p}_{refp,cmn,cmp}`, four `pfet_01v8` and two
`nfet_01v8`). Those are **not standard cells**: `klt place-and-route` places
`sky130_fd_sc_hd` instances on a `unithd` site grid and has no notion of a MiM
capacitor or a hand-sized analog switch, and the network's `BOT_OFF_N`/
`BOT_OFF_P` plates sit on the comparator's own `TOP_N`/`TOP_P` input nodes, so
its placement is an analog-floorplan question rather than a row-placement one.
It therefore needs a hand-drawn flow of its own, in the shape of
`layout/sampling-frontend/` (device generators + `klt draw` + `klt
gen-compose`), not an extra module in this bank. **Filed separately — see
"Remaining work" below.** Until it lands, this block covers 33 of the 41
top-level instances and the other 8 still have no drawn geometry anywhere
under `layout/`.

`DOUT9N` is deliberately **not** a port of this macro: nothing outside it
consumes the sign-bit complement, so it stays internal and the top-level
composition never has to route it. `klt extract` reports exactly this (one net
"kept internal: no drawn label on the net matches the DEF's own declared PINS
set"), which is the intended outcome, not a gap.

## Status: DRC-clean, LVS-clean

`reports/LATEST`'s record:

| Verdict | Result |
| --- | --- |
| `bin/check-schematic-parity.py` | **OK** — 33 instances, 6 cell types, every pin net-identical to `design/sar_adc_top.spice` |
| `klt place-and-route` | reaches `route`, 0 setup/hold violations |
| `klt drc --deck sky130` | **CLEAN**, 0 violations |
| `klt lvs` | **match**, 234/234 devices, 134/134 nets, 48/48 pins |

The 9 informational `topology` entries `lvs.json` reports are the same
"ambiguous pairing resolved structurally" warnings every symmetric bank in
this repo produces (`layout/seln-inverters/` reported 9 of them for nine
electrically-identical inverters; `layout/sar-sequencer/` the same kind) — here
they fall on the internal source/drain nodes of the eighteen structurally
identical `SELn<i>`/`SELp<i>` AND gates. Severity `warning`, `error_count: 0`,
verdict `match`.

## The parity gate is the point of this directory (issue #387)

**A clean `klt lvs` match on this flow does not, on its own, establish that the
geometry implements the schematic.** The LVS reference is *generated from the
same post-route netlist the GDS was routed from*
(`bin/generate-lvs-reference.py`), so the two sides of the compare are not
independent: they agree with each other whatever they both say. Issue #56's
`SELp<i> = DOUT<i>` / `SELn<i> = NOT(DOUT<i>)` glue stayed in
`layout/seln-inverters/` for two weeks after DR-008 superseded it (2026-09-11,
issue #263 / PR #266), through repeated DRC-clean / LVS-match runs, for exactly
this reason. Nothing in the chain could see it: the citation gate's check 10
grades the top-level *port list*, and DR-008 moved no port.

`bin/check-schematic-parity.py` supplies the missing independent anchor. It
re-derives the expected instance list from `design/sar_adc_top.spice` —
translating each positional SPICE card against the PDK's own `.SUBCKT` pin
order — and diffs it against `netlist/top_glue.v` instance by instance, pin by
pin, net by net. A polarity swap (one `and2_1` input moved from `DOUT9N` back
to `DOUT9`) fails it; the superseded inverter-bank netlist fails it.

Three properties make it a gate rather than a comment:

1. **It is a hard failure in `run-flow.sh`, before the record directory is
   created.** A drifted netlist cannot mint a record at all, so no future
   reader can cite a DRC/LVS verdict over geometry built from the wrong
   topology. It runs a second time on the *post-route* netlist, so the router
   cannot add, drop or rename an instance on the way to the GDS either.
2. **It is always-on in CI**, via `npm run check:glue-parity` inside
   `check:ci` — not nightly, because the drift it catches is invisible to
   every verdict this repo records, and two weeks of clean runs is what that
   invisibility already cost. The one PDK-derived input (each cell's `.SUBCKT`
   pin order) is cached in `netlist/sky130_fd_sc_hd-pin-order.json` and
   *verified* against the real CDL on every run that has a PDK, so the cache
   cannot drift silently either.
3. **The check itself is pinned by tests.**
   `sim/tests/test_top_glue_schematic_parity.py` asserts it passes on the
   committed netlist and fails on: the DR-008 polarity swap, the historical
   `layout/seln-inverters/netlist/seln_inverters.v`, a dropped instance, an
   extra instance, and a drifted implicit supply connection.

`design/sar_adc_top.spice` is itself gated against the schematic sources by
`design/regen_netlist.sh --check` in CI's `pdk-smoke` job, so the chain is
schematic → netlist → parity gate → Verilog → GDS with no self-reference at
any link.

## Which `klt` flow, and why

`klt place-and-route` (OpenROAD), the same choice `layout/sar-sequencer/` and
the superseded `layout/seln-inverters/` make and for the same reason:
`netlist/top_glue.v` is a **hand-derived 1:1 structural transliteration** of
`design/sar_adc_top.spice`'s own instance lines, not RTL — there is nothing for
`klt synthesize` to usefully do, and synthesis would be free to restructure
exactly the polarity the parity gate exists to hold fixed.

**No clock, no state — but the request schema still requires
`constraints.clock_port`/`clock_period_ns`.** All 33 cells are combinational,
so `requests/place-and-route.json` declares a placeholder clock net name
(`CTS_NO_SUCH_CLOCK`) that appears nowhere in the netlist, purely to satisfy
that required field. Naming a *real* net instead reproducibly segfaults `klt
place-and-route`'s `cts` stage (OpenROAD exit 139) once that net has zero
fanout to any sequential cell — filed generically as
`2AMLogic/klayout-tools#1506`; the nonexistent-net workaround takes
`clock_tree_synthesis`'s no-op path instead. Carried over verbatim from
`layout/seln-inverters/README.md`, which met it first.

**`io.layer_v` must name a layer the router actually draws on.** The first run
of this flow used `{"layer_h": "met1", "layer_v": "li1"}`, copied from
`layout/seln-inverters/requests/place-and-route.json`, and reached `route` with
a **clean DRC and a `match` LVS verdict while extracting only 2 of its 48
top-level pins** (`extract.json` `pin_count: 2`). The sibling never hit it
because with only 18 signal pins OpenROAD placed every one of them on the
left/right edges, i.e. on `layer_h` = met1. With 46 signal pins spread over all
four edges, the top/bottom ones landed on li1 — and OpenROAD writes a DEF
`PINS` port's geometry to the `li1.label` layer (`67/16`), which the sky130
extraction deck lists as outside its connectivity graph, while drawing no
`li1.drawing` (`67/20`) conductor there at all. The label therefore sits on
nothing, the net is never promoted, and `--def-pins` reports "no drawn label on
the net matches the DEF's own declared PINS set". Verified directly on the
first run's own GDS: 46 texts on `67/5`, 46 shapes on `67/16`, **zero** shapes
on `67/20`. Moving to `{"layer_h": "met1", "layer_v": "met2"}` — both layers
the router draws real conductor on — reaches 48/48/48 pins with no other
change. Filed generically as `2AMLogic/klayout-tools#2473` (see "Upstream
filings").

**That li1 run is retained as its own record,
`reports/20260925-043546-0259924/`, and is NOT a signoff record.** It is kept
because it *is* the evidence for the paragraph above and for the upstream
filing: its `extract.json` reports `pin_count: 2` beside a `clean` DRC and a
`match` LVS verdict — exactly the "silently passes while 46 of 48 declared pins
do not electrically exist" shape being reported. `reports/LATEST` points at the
met2 run; cite that one for any verdict.

Floorplan utilization is 5 % requested / 6.7 % achieved (die 5163 µm², ~71.9 µm
square) rather than a dense 45 %: `klt place-and-route`'s PDN generator needs
enough die width for full-width met4/met5 straps (sky130's `met4`/`met5`
minimum width is 1.6 µm) with real margin, and this block needs a *connected*
`VPWR`/`VGND` PDN — not the row-rail-only obstruction `klt place-and-route`
draws when `power` is omitted — or LVS is unreachable independent of any `klt`
gap. The strap geometry (met1 followpins + met4/met5 at 27.14/27.2 µm pitch) is
reused verbatim from `layout/sar-sequencer/` and `layout/seln-inverters/`, both
of which closed DRC/LVS on it. Area was not a goal here; this macro's isolated
DRC/LVS closure was.

## LVS reference provenance

Same mechanism as `layout/sar-sequencer/bin/generate-lvs-reference.py` (issue
#102): `klt extract --deck sky130` is a flat, transistor-level extractor, so
the LVS reference has to be flat and transistor-level too, with every drawn
NMOS/PMOS generalized to `klt`'s own `nfet`/`pfet` device classes.
`bin/generate-lvs-reference.py` flattens the **post-route** structural Verilog
netlist (`klt place-and-route`'s own `write_verilog` dump) against the sky130
PDK's own official per-cell CDL model (`sky130_fd_sc_hd.cdl`, Apache-2.0,
SkyWater's own release — not reverse-engineered), via the shared
`layout/bin/_lvs_reference_common.py` core, widened here from one cell type to
six. It additionally asserts its own per-cell-type instance census before
emitting anything, so a silently-dropped instance fails rather than quietly
minting a reference that matches a layout that matches nothing else.

## Running the flow

```sh
layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
source sim/env.sh                     # exports PDK_ROOT/PDK
layout/top-glue/bin/run-flow.sh       # ~2 minutes; parity -> P&R -> DRC -> LVS
```

Requires an `openroad` binary on `$PATH` (see `docs/environment-setup.md`).
Each run mints a new timestamped, append-only record under
`reports/<record-id>/` (same convention as `layout/trivial-cell/reports/`), and
`reports/LATEST` points at the newest one.

## Files

```
layout/top-glue/
  README.md                          # this file
  netlist/
    top_glue.v                       # hand-derived structural netlist (not RTL)
    sky130_fd_sc_hd-pin-order.json   # PDK .SUBCKT pin orders, cached for the headless gate
  requests/
    place-and-route.json             # klt place-and-route request
  bin/
    run-flow.sh                      # parity gate -> place-and-route -> DRC -> post-route netlist
                                     # dump -> parity gate again -> LVS reference -> extract
                                     # --def-pins -> LVS -> record
    check-schematic-parity.py         # the independent anchor -- see the section above
    generate-lvs-reference.py         # flattens the post-route netlist against the PDK's own CDL
    render-record.py                  # renders record.md from the JSON envelopes run-flow.sh produced
  reference/                          # generate-lvs-reference.py's own output -- regenerated per run, git-ignored
  reports/
    LATEST                            # record-id of the most recent run
    <record-id>/                      # append-only: netlist, request, routed GDS/DEF, post-route netlist,
                                      # schematic-parity.txt (pre- AND post-route verdicts),
                                      # generated LVS reference, every klt JSON envelope, record.md
```

## Relationship to `layout/seln-inverters/`

`layout/seln-inverters/` is this block's **superseded predecessor** — nine
`inv_1` cells implementing issue #56's `SELn<i> = NOT(DOUT<i>)`, a wiring
DR-008 retired. It is kept in the tree, marked superseded in its own README,
only because `layout/sar-adc-top/`'s composition still consumes its GDS. It is
retired (and its records left as append-only history) by the top-level
recomposition that replaces it with this block, issue #401 — see below.

## Remaining work before the top level means anything

This block is one of the three pieces issue #387 identified. The other two are
filed separately and this directory does **not** claim them:

- **DR-009's half-LSB offset network** (the 8 `sky130_fd_pr` primitives above)
  still has no drawn geometry — issue #400.
- **`layout/sar-adc-top/`'s composition and its LVS reference** still implement
  issue #56's superseded glue: `build_layout.py` still places
  `seln_inverters`, and `generate-lvs-reference.py`'s `TOP_SUBCKT` wrapper
  still wires each `SELp<i>` straight to `DOUT<i>`. Until that is re-derived
  from `design/sar_adc_top.spice` as it stands, a device-level match on the
  composed GDS would not establish that it implements this repo's schematic —
  which is the load-bearing point of issue #387 and is unchanged by this
  directory existing — issue #401.

## Upstream filings (`klayout-tools`, per CLAUDE.md's friction protocol)

- The `io.layer_v` / extraction-deck pin-layer mismatch described under "Which
  `klt` flow, and why": a P&R request option whose accepted value silently
  produces top-level pins the companion `klt extract` cannot see, with a clean
  DRC and a `match` LVS verdict to cover for it. Filed generically (no design
  detail) as `2AMLogic/klayout-tools#2473`.
- `2AMLogic/klayout-tools#1506` (the `cts` segfault behind the
  `CTS_NO_SUCH_CLOCK` placeholder) is pre-existing and was filed by the
  predecessor block, not this one.

## Provenance

Structure follows `layout/sar-sequencer/`'s and `layout/seln-inverters/`'s own
conventions (append-only timestamped records, `reports/LATEST` pointer,
`record.md` provenance stamping, CDL-based flat LVS reference generation),
widened to six cell types and given the schematic-parity gate those two lack.
Clean room: the topology placed and routed is this repo's own
`design/sar_adc_top.spice` and its own decision records (DR-008, DR-009); the
only external inputs are the sky130 PDK's own official, freely-licensed
standard-cell library and OpenROAD's own placement/routing algorithms.

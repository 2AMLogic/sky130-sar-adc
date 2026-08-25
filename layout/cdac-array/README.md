# cdac-array/ — differential CDAC array layout (issue #100)

Physical layout for the differential charge-redistribution CDAC array
(`design/cdac/cdac_array.sch`) and its unit cell
(`design/cdac/cdac_unit_cell.sch`), drawn full-custom with `klt`'s
draw → DRC → extract → LVS flow.

```sh
layout/bin/setup-venv.sh              # once, or after bumping requirements.txt
source sim/env.sh                      # exports PDK_ROOT/PDK for xschem
layout/cdac-array/bin/run-flow.sh      # ~6 seconds; exit 0 iff all eight verdicts hold
cat layout/cdac-array/reports/$(cat layout/cdac-array/reports/LATEST)/record.md
```

## Files

```
layout/cdac-array/
  bin/
    cdac_layout.py             # the generator: emits both top cells' GDS
    generate-lvs-reference.py  # xschem-netlists design/cdac/*.sch -> LVS reference
    render-record.py           # renders record.md, asserts the eight verdicts
    run-flow.sh                # draw -> DRC -> extract -> LVS, one record per run
  reference/
    cdac_array.lvs-reference.spice      # GENERATED from the schematic
    cdac_unit_cell.lvs-reference.spice  # GENERATED from the schematic
  reports/
    LATEST                     # record-id of the most recent run
    <record-id>/               # append-only: the GDS, drc/extract/lvs/draw JSON,
                               # the extracted netlist, the reference, record.md
```

Records follow `sim/`'s and `layout/trivial-cell/`'s append-only rule: a
re-run mints a new `<YYYYMMDD>-<HHMMSS>-<short-sha>` directory and never
edits an existing one.

## What the flow asserts

`run-flow.sh` exits non-zero unless **all eight** of these hold, every one
read out of `klt`'s own JSON envelope rather than off a process exit code:

| # | Verdict |
| --- | --- |
| 1 | `klt drc` **clean** on `cdac_unit_cell` |
| 2 | `klt lvs` **match** on `cdac_unit_cell` vs. `design/cdac/cdac_unit_cell.sch` |
| 3 | `klt drc` **clean** on `cdac_array` |
| 4 | `klt lvs` **match** on `cdac_array` vs. `design/cdac/cdac_array.sch` |
| 5 | `klt extract` finds exactly 1024 MiM caps + 18 nfet + 18 pfet in `cdac_array` |
| 6 | Every bit 8..1 has its unit-cap centroid exactly on the array's centre in Y |
| 7 | Bits 8..4 additionally have it exactly on the centre in X |
| 8 | Every bit's P-side and N-side X centroids coincide |

Verdicts 5–8 exist because **1–4 do not say what they look like they say**.
`klt lvs`'s `combine_devices` folds `w` parallel unit capacitors into a
single device *before* comparing, so an LVS match is equally happy with one
scaled plate per bit as with `w` unit elements — and neither DRC nor LVS
has any opinion at all about where those elements sit. Verdict 5 pins the
unit-element decomposition using the *pre-combination* device count;
verdicts 6–8 pin the placement using centroids computed from the same
placement functions the geometry is drawn from. Without them, a
matching-poor rewrite of this generator would sail through 1–4.

The LVS reference is **regenerated from the schematic on every run**
(step 0 of `run-flow.sh`), never trusted from the committed copy: a match
against a stale reference proves nothing about today's schematic.

---

# The matching strategy

This is the block's matching-critical sub-block: its unit-capacitor ratios
*are* the converter's INL/DNL, and no amount of DRC/LVS cleanliness speaks
to them. What follows is the deliberate strategy, stated so it can be
argued with — and, where it is measurable, measured in each record.

## 1. Unit elements, never scaled plates

`design/cdac/cdac_array.sch` writes bit `i`'s weight as `MF=2**i` on one
`cap_mim_m3_1` symbol, and `design/cdac/README.md` is explicit that this is
netlist shorthand for `2**i` *parallel unit cells*, "**NOT** a claim about
physical placement". This layout takes that literally: **1024 physically
identical unit capacitors**, 512 per side, one drawn unit per unit of
weight. Every one of them is the same shape — same 1.898 µm capm plate,
same met3 bottom plate, same via2 position, same via1/met1 stub geometry —
so that whatever the process does to one unit, it does to all of them.

This is not merely stylistic. sky130's MiM model (and `klt extract`'s deck)
carries a **perimeter** term as well as an area term, so a single plate of
`w` times the unit area is *not* `w` unit capacitors: it has
`√w` times the perimeter, not `w` times. Ratio accuracy in a
binary-weighted CDAC depends on the weights being exact multiples, and only
a unit-element decomposition delivers that by construction. (It also means
the LVS reference for a bit of weight `w` is exactly `w × C_unit`, which is
what `generate-lvs-reference.py` emits.)

## 2. Common centroid in X: dyadic mirror-pair columns

The array is 64 columns × 16 rows on a 3.4 µm pitch, so a column holds 8
units per side. Bits 8..4 own 32/16/8/4/2 columns, always as
**mirror-symmetric pairs about the array's vertical centre line**, and each
bit's columns are spread with a *dyadic* ("ruler") interleave — the largest
bit takes every other column slot, the next takes every other remaining
slot, and so on:

```
h (distance rank from the centre): 0  1  2  3  4  5  6  7  8 ...
bit owning that column:            8  7  8  6  8  7  8  5  8 ...
```

The mirror pairing cancels a **linear** X gradient exactly (verdict 7). The
dyadic spread is what makes the arrangement robust to a **quadratic**
(bowl-shaped) gradient as well: every bit samples the same distribution of
distances from the centre, so a bowl scales every bit's weight by
approximately the same factor — a gain error, not a nonlinearity, and gain
errors do not cost INL or DNL.

## 3. Differential interleave in Y, with a parity flip at the midline

Rows alternate P/N so that a Y gradient sees both sub-arrays equally. A
naive strict alternation would still leave the P set and the N set offset by
one row pitch (P on rows 0,2,4,… averages one row below N on 1,3,5,…), so
the parity **flips at the array's horizontal midline**: P owns the even rows
in the lower half and the odd rows in the upper half. The two sides' Y
centroids then coincide exactly, for every bit (verdict 6 and the record's
own centroid table).

Because P and N share the *same columns* for every bit, their X centroids
coincide by construction too (verdict 8) — a differential pair of
sub-arrays placed side by side, rather than interleaved, would instead have
its whole differential gain riding on the X gradient between the two halves.

## 4. The residuals, stated plainly

A binary-weighted array has a smallest element that cannot be split
symmetrically. Ours are:

- **bit3** owns a single column (col 31) and the
  **bit2+bit1+bit0+termination group** owns a single column (col 32). They
  sit either side of the centre line, so their X centroids are ∓1.7 µm
  (half a column pitch) rather than 0. The two offsets are equal and
  opposite, so the *side total* is still centred; the residual is a
  1.7 µm lever arm on groups worth 8 and 8 units out of 512.
- **bit0 and the termination unit** are one unit per side, so their P/N
  pairs are one row pitch (3.4 µm) apart in Y rather than coincident. This
  is the minimum achievable separation for a single-unit bit.

Both residuals are printed in every record's centroid table, not hidden.

## 5. The guard frame — and why it carries no capm

The array is ringed by one row/column of **guard plates**: the identical
met3 bottom-plate geometry and via2 landing as a real unit, tied to VREFN
(left/right/top collected on met2, the bottom row on met1 so its collector
does not have to cross 128 column straps on their own layer), but with the
**MiM top plate omitted**.

The omission is forced, and it is worth being blunt about the consequence:

- Under `klt` 0.3.0's sky130 extraction deck, *any* capm drawn over met3 is
  recognised as a capacitor device. The deck's dummy-device marker layer
  (`(83, 20)`, which suppresses drawn-but-non-functional MOS, resistor,
  bipolar and diode devices) is **not** consulted for drawn capacitors, so a
  capm-bearing dummy cannot be suppressed. Nor can it be neutralised by
  shorting its plates: the deck's `top_plate_via` overlap exclusion removes
  *every* via3-on-met3 overlap in the layout once any capm exists, so met4
  cannot be routed down to met3 anywhere, and a dummy's top plate has no
  path back to its own bottom plate.
- The result is that a capm dummy ring would appear in the extracted netlist
  as extra capacitors with no schematic counterpart — i.e. it would trade an
  LVS-clean result (an acceptance criterion of issue #100) for an
  etch-density guard.

So this layout guards the **bottom-plate (met3) level** — pattern density,
plate-edge lithography and the etch environment of the outermost active
plates — and leaves the **capm level** unguarded. What that costs is
bounded and uniform in the direction that matters: every column contributes
exactly one unit per side to each of the two edge *rows*, so a
row-edge effect is a pure gain term shared by all bits, with no INL/DNL
contribution. Only the two edge *columns* are bit-specific, and they carry
32 units per side out of 512.

Per `CLAUDE.md`'s friction protocol both tool gaps above are filed
**generically** at `2AMLogic/klayout-tools` — tool behaviour only, no
design detail: klayout-tools#1387 (the `dummy` marker is not honoured for
drawn capacitors) and klayout-tools#1388 (the top-plate-via exclusion is
chip-wide on a zero-oversize deck, so one drawn cap disconnects every
ordinary via between the bottom-plate metal and the metal above it). A
future `klt` that closes #1387 would let this ring grow a capm plate with
no other change to the generator — `draw_unit_cap(..., capm=False)` is a
one-flag switch — and the guard plates would then need only the deck's
dummy-marker layer added on top.

## 6. What this layout does *not* claim

- **No matching evidence.** Nothing here measures σ(ΔC/C), INL or DNL. The
  strategy above is an argument from symmetry, plus centroid arithmetic; the
  evidence is a Monte-Carlo mismatch campaign (issues #28/#29) run against
  a netlist that instantiates literal parallel unit cells. `design/cdac/
  README.md` §3 already flags that an `MF`-scaled schematic netlist may
  understate array mismatch if ngspice scales one mismatch term instead of
  drawing `w` independent ones — this layout is exactly the `w` independent
  units that concern is about.
- **No parasitic extraction.** `klt extract`'s device recognition is not an
  RC extraction; the met2 bottom-plate straps and met4 top-plate rails carry
  real parasitic capacitance to the top plates that is not in any number
  here.
- **No routing-parasitic balancing.** The per-bit strap lengths differ
  (a bit's straps run from its own columns to its own bus row), so the
  bottom-plate wiring capacitance is *not* matched between bits. It sits on
  the bottom plate, which is driven hard to VREFP/VREFN by the switch, so it
  costs settling time rather than charge accuracy — but it is unbalanced and
  unquantified, and a future revision that cares should say so with numbers.
- **No spec ratification.** `C_u`, `V_REF` and everything derived from them
  are DRAFT pending issue #27; this layout consumes DR-003 Item 3's
  provisional 1.8988 µm plate and would be regenerated, not patched, if that
  changes.

## Provenance

Flow structure (record convention, "assert verdicts from the JSON envelope,
never the exit code", `setup-venv.sh` reuse) follows
`layout/trivial-cell/`'s own flow in this repo, which was in turn ported
from `2AMLogic/sky130-bandgap` per `CLAUDE.md`'s harness-bootstrap
instruction. The layout itself is drawn from `design/cdac/*.sch` and device
physics only — clean room, per `CLAUDE.md`: no other party's CDAC
implementation was consulted, measured, netlisted or reconstructed.

## Tool-pin note

This sub-block requires `klayout-tools` **0.3.0** (bumped from 0.2.0 in
`layout/requirements.txt` by this work). 0.2.0's sky130 extraction deck
stops its `metals`/`vias` connectivity at met1, so a MiM-cap array — whose
bottom plates live on met3 and whose top-plate rails live on met4 — is not
extractable at all on that pin. The bump has one piece of fallout outside
this directory: `layout/trivial-cell/reference.spice` carried 8 M-cards
because 0.2.0 could not tell a dummy MOS from a real one, and 0.3.0 can, so
that reference is now 4 M-cards. Its header records the change; the
six-verdict trivial-cell flow passes on the new pin.

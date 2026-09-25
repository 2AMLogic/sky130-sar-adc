# `sim/ground-return-impedance/` — supply-terminal and ground-return impedance

The testbench [DR-012](../../spec/decision-records/DR-012-analog-ground-pad.md)
(issue #362) named as its own open item, and issue #378 tracks. DR-012 decided
the block presents a **drawn** analog `GND` pad rather than reaching board
ground through the substrate only. It argued that from the design's topology
and from device physics, and it said so in its own words, because **every
campaign in `sim/` drove all four supply terminals from ideal zero-impedance
sources**: no package parasitics, no substrate resistance, no bond-wire
inductance. This campaign is the measurement.

It runs `sim/full-conversion-transient/`'s own whole-ADC stimulus on the
assembled `design/sar_adc_top.spice`. The four supply terminals (`VDD`, `GND`,
`VPWR`, `VGND`) go through package-like series R+L, and a lumped substrate
resistance joins the analog and digital grounds on die. Each input's captured
code is then compared against the ideal-source case at the **same** PVT point,
over the ratified 9-point one-at-a-time grid.

## Cold start

```sh
source sim/env.sh                                                        # PDK_ROOT / PDK
python3 sim/ground-return-impedance/run_ground_return.py --check-env      # toolchain + PDK pin
python3 sim/ground-return-impedance/run_ground_return.py --list-arms      # the arms and the package values

# the recorded campaign (8 arms x 9 ratified OAT points + the rename control):
SIM_NGSPICE_TIMEOUT_S=3600 python3 sim/ground-return-impedance/run_ground_return.py --corners --record --jobs 12
```

Other invocations:

```sh
python3 sim/ground-return-impedance/run_ground_return.py                       # every arm, baseline corner only
python3 sim/ground-return-impedance/run_ground_return.py --arms pkg,pkg-nopad-1k # a subset (ideal is always added)
python3 -m unittest sim.tests.test_ground_return                               # PDK-free deck-rewrite tests
```

**Runtime.** One point is the same ~6.3 µs whole-ADC transient as
`sim/full-conversion-transient/`. The package arms run slower than the ideal
arm, because the ~2 nH / small-capacitance die nodes ring and the adaptive
timestep has to follow them. Expect 5–15 minutes per point on a contended
machine. The recorded campaign is 73 runs; `--jobs` changes wall-clock time
only.

On a heavily contended host a package point can take more than two hours of
wall-clock time. A point that exhausts its retries raises and ends the whole
invocation, and every finished point is then lost. To avoid that, pass
`--cache-dir DIR` (any scratch directory outside the repo) together with a
generous `SIM_NGSPICE_TIMEOUT_S`. Each finished point's raw ngspice log is
kept there, keyed on the sha256 of the exact deck text plus the ngspice version
and PDK revision. A re-run of the same command then reuses those logs and only
simulates what is missing. A log is reused only for a byte-identical deck on
the same toolchain. The record states how many of its runs were reused, and
every raw log, reused or not, is committed under `corners/`:

```sh
SIM_NGSPICE_TIMEOUT_S=21600 python3 sim/ground-return-impedance/run_ground_return.py --corners --record --jobs 24 --cache-dir /tmp/gri-cache
```

## What is reused, and the two deck rewrites

The DUT, the stimulus/measurement fragment
(`sim/full-conversion-transient/testbench/full_conversion_tb_fragment.spice`),
the deck assembly (`run_conversion.assemble_deck()`), the code decoder
(`run_conversion.decode()`) and the ratified grid are all **imported
read-only** from `sim/full-conversion-transient/`. This campaign edits none of
them. It adds two **testbench-only** rewrites of the assembled deck text. Both
are pinned by `sim/tests/test_ground_return.py`, and neither is ever written
back to `design/`:

1. **`GND` → `GND_DIE`.** This is load-bearing. ngspice treats a node named
   `gnd` as an alias of the reference node `0`. In every existing campaign the
   analog ground is therefore not just *ideal*: it *is* the simulator's
   reference, and nothing can be placed in series with it. The rename works on
   whole tokens, is case-sensitive (so `VGND` is untouched) and skips comment
   lines. It fails loudly if any ground-aliased `gnd` token survives, because
   a survivor would silently keep that device's ground ideal and produce a
   plausible-looking "no effect".
2. **Supply sources re-pointed.** The fragment's `VVDD`/`VVPWR`/`VVGND` lines
   are replaced by each arm's network, and a fourth source `VVGNDA` is added
   for the analog ground pad. Source names are unchanged, so the fragment's
   own `avg i(vvdd)` and `avg i(vvpwr)` measurements still resolve.

**Controls, mechanical, reported in every record.** The ideal arm's `GND_DIE`
must be exactly 0 V. Every package arm's `GND_DIE` must move by more than
0.1 mV p-p, which proves the network is actually in the circuit. The
**rename control** runs the *unrenamed* as-committed deck, exactly as
`sim/full-conversion-transient/` assembles it, and its codes must equal the
ideal arm's at the same corner, which proves on the simulator that the rename
changed nothing. Finally, every measurement must be present at every point.

## The arms

| arm | package R+L | GND pad | `R_sub` | isolates |
|---|---|---|---|---|
| `ideal` | ideal | bonded | — | baseline: what every existing campaign runs |
| `pkg` | yes, all 4 | bonded | — | bond R+L alone, grounds separate on die (the schematic's two-net view) |
| `pkg-sub10`, `pkg-sub1k` | yes, all 4 | bonded | 10 Ω / 1 kΩ | **the pad as DR-012 decided it**: bond R+L plus the substrate joining the grounds |
| `sub-nopad-10`, `sub-nopad-1k` | ideal | **none** | 10 Ω / 1 kΩ | substrate resistance alone, with no inductance anywhere: "on-die substrate return" separated from "bond inductance" |
| `pkg-nopad-10`, `pkg-nopad-1k` | yes, 3 bonded | **none** | 10 Ω / 1 kΩ | **DR-012's rejected null option** under a package: analog ground reaches the outside only through the substrate to `VGND` |

In the no-pad arms, `GND_DIE`'s only DC path is the substrate resistance to
die-side `VGND`. That is DR-012's own measured fact: `GND` and `VGND` are one
extracted net through the p-substrate (`GND|VGND`,
`layout/sar-adc-top/reports/20260924-214710-b323061/extract.json`), reduced
to one resistor. No backside/die-attach path is modelled, because DR-012 notes
that nothing in this repo specifies one.

## Where the R+L values come from

These are **testbench stimulus parameters**, recorded as a decision in
[DR-015](../../spec/decision-records/DR-015-testbench-package-model.md). They
set no spec row. They are derived here from geometry and bulk material
constants, not taken from any package datasheet or any other party's design:

- **One bond wire per supply terminal: 25 µm diameter gold, 2 mm long.** 25 µm
  (1 mil) is the common wire gauge for fine-pitch ball bonding. 2 mm is a
  representative die-edge-to-lead span for a small die. Both are assumptions,
  stated as such.
- **L = (µ0·l / 2π)·(ln(2l/r) − 3/4) = 2.01 nH.** This is the low-frequency
  self-inductance of an isolated straight round wire (l = 2 mm, r = 12.5 µm).
  It leaves out mutual inductance to neighbouring wires, which *lowers*
  effective loop inductance for adjacent supply/return pairs and *raises* it
  for same-direction pairs. It also leaves out package leads and the board.
- **R = ρ·l / A = 0.099 Ω.** DC value, bulk Au ρ = 2.44×10⁻⁸ Ω·m. Skin effect
  raises the real value at GHz. Using the DC value *under-damps* the package
  LC, which is the pessimistic direction for supply ringing.
- **`R_sub` ∈ {10 Ω, 1 kΩ}: a bracket, not a value.** 10 Ω is the low end of
  DR-012's own "10s of ohms" wording, and 1 kΩ is two decades above it. No
  substrate network has been extracted in this repo, so no single number could
  be defended. Running both ends makes any conclusion that holds at both
  independent of where in that range the real value falls. It does not make
  either number physical.
- **Board side is ideal** (sources to node `0`, no board impedance, no board
  decoupling), and **no on-die decoupling** is modelled, because none exists
  in this design (a DR-010/DR-012 open item). Without on-die decoupling, the
  only thing holding a die rail up during a current step is the die's own
  device/wiring capacitance.

**Why a decision record.** Issue #378 says a package-style assumption is a
decision. [DR-015](../../spec/decision-records/DR-015-testbench-package-model.md)
records these values as **stimulus**. They are not a claim about which package
the block ships in, and nothing is graded against them as a threshold. A later
supply campaign cites DR-015 rather than copying this README's numbers. If a
package is ever *chosen* (with a real lead frame and a board), that choice
supersedes DR-015, and this campaign should be re-run with its numbers.

## What this can and cannot claim

- **Can:** whether, at this stimulus and these network values, any captured
  code moves when the ideal sources are replaced by the networks above, at
  every ratified PVT point. It also shows how far each die node bounces
  against board ground while that happens.
- **Cannot:** what a real package or substrate does. The bond wire is one
  first-principles geometry, and `R_sub` is one lumped resistor at two
  bracketing values, not an extracted substrate network.
- **Cannot speak to references.** `VREFP`/`VREFN`/`VCM` stay ideal and
  board-referenced. The CDAC's switching charge returns through `VREFN`, not
  through any of the four terminals graded here. Reference-pin impedance is a
  separate question.
- **Five DC inputs, one clock rate.** A code that does not move here does not
  prove immunity at other inputs, or at a dynamic (sine) input.
- **The baseline itself is not correct at full scale.** The `ideal` arm
  inherits the design's standing near-full-scale failure (issues #265/#267),
  so this campaign grades the *change* in each code against the ideal arm,
  never the code against the ideal code.

## Directory contents

| Path | What |
|---|---|
| `run_ground_return.py` | Arms, the two deck rewrites, the corner loop, controls, and record writing. |
| `netlist-snapshots/<record-id>.spice` | The UNMODIFIED DUT the record was produced from. |
| `corners/<record-id>/<arm>__<corner-id>.log` | Raw ngspice output, one per arm per PVT point, plus `rename-control__<corner-id>.log`. |
| `corners/<record-id>/decks/<arm>__<corner-id>.spice` | Each arm's fully assembled (rewritten) deck at the baseline corner, so the exact network is readable without re-running anything. |
| `records/<record-id>.md` | The append-only evidence record. `records/LATEST` names the newest. |

## Findings

Read `records/LATEST` for the numbers. The first record's reading is below.

**`records/20260925-134451-5b3f175.md`** (8 arms × 9 ratified PVT points, plus
the rename control; all four controls pass):

| arm | codes moved vs `ideal` | worst GND_DIE p-p (mV) | worst min VDDA (/ V_DD) |
|---|---|---|---|
| `pkg` | 4/45 | 259.0 | 0.965 |
| `pkg-sub10` (pad, as decided) | 4/45 | 129.0 | 0.948 |
| `pkg-sub1k` (pad, as decided) | 3/45 | 229.6 | 0.959 |
| `sub-nopad-10` | 0/45 | 7.2 | 0.997 |
| `sub-nopad-1k` | 3/45 | 429.3 | 0.831 |
| `pkg-nopad-10` (null option) | 4/45 | 183.1 | 0.953 |
| `pkg-nopad-1k` (null option) | 7/45 | 402.9 | 0.851 |

1. **No code moves by more than 1 LSB, in any arm, at any point.** Every move
   lands on one of two inputs. The first is `+0.00·V_REF`, where the ideal arm
   itself sits on the 511/512 boundary (it reads 512 at `sf`, `-40c` and
   `125c`, and 511 elsewhere). The second is `-0.78·V_REF`, which the ideal
   arm already misses by 71–124 LSB at every point (the #265/#267 baseline
   failure). The `-0.25`, `+0.25` and `+0.78` inputs never move, in any arm,
   at any point.
2. **The pad lowers analog-ground bounce at both ends of the `R_sub`
   bracket.** With the package on, bonding `GND` cuts the worst `GND_DIE`
   p-p from 183.1 to 129.0 mV at 10 Ω, and from 402.9 to 229.6 mV at 1 kΩ.
   The droop in the analog supply the devices actually see (`VDDA`) depends
   on where in the bracket `R_sub` falls: about equal at 10 Ω (0.948 vs 0.953
   of `V_DD`), and much better with the pad at 1 kΩ (0.959 vs 0.851).
3. **At the code level the pad's benefit is visible at only one end of the
   bracket.** At 1 kΩ the null option moves 7/45 codes and the pad moves
   3/45. At 10 Ω both move 4/45. By DR-015's own rule (a conclusion counts only
   if it holds at both ends), this record does **not** show a code-level
   benefit from the pad.
4. **Bond inductance, not the substrate return, dominates at the low end.**
   Substrate resistance alone at 10 Ω with ideal bonds (`sub-nopad-10`) moves
   nothing and bounces 7.2 mV. Adding the package with the pad bonded brings
   3–4/45 moves and 129–259 mV of worst-case bounce (`pkg`, `pkg-sub10`,
   `pkg-sub1k`). With no on-die decoupling
   in the design, a bonded pad does not remove that (see DR-010's open item).

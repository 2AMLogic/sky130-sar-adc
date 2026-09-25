# DR-015: Supply-return testbenches use a stated first-principles bond-wire model and a bracketed lumped substrate resistance. This is a stimulus assumption, not a package choice

- **Status**: proposed. Like DR-012 and DR-013, this record sets no numeric row
  of `spec/target-spec.md`. It fixes the **testbench stimulus** that one
  campaign (and any later supply-impedance campaign that cites it) drives the
  block with. It inherits the same provisional status as every record still
  resting on DR-003's DRAFT numeric inputs.
- **Date**: 2026-09-24
- **Decided by**: Builder agent, issue #378
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #378 (the campaign this record serves), #362 / DR-012 (whose
  "the impedance argument is unmeasured" open item that campaign retires),
  #377 / DR-013, DR-010 (the digital supply partition; the on-die decoupling
  open item), `sim/ground-return-impedance/` (the campaign, its README's
  derivation, and its records), `sim/vcm-drive-budget/` (the precedent for
  a campaign-stated source-impedance assumption).

## Context

DR-012 decided that the block presents a drawn analog `GND` pad. It argued the
benefit from topology and device physics. Until #378, every `sim/` campaign
drove all four supply terminals (`VDD`, `GND`, `VPWR`, `VGND`) from ideal
zero-impedance sources, so no testbench had put any impedance in the return
path. To measure DR-012's argument, a testbench has to put *some* package
impedance on those terminals. Issue #378 says plainly that choosing it is a
decision: *"a package style assumption is a decision — if it needs ratifying,
it needs a DR."* This is that record.

**Verified:** there is no package, lead frame, board, or die-attach
specification anywhere in this repo. `spec/target-spec.md` has no
supply-impedance row. DR-012 notes that nothing specifies a backside path. No
substrate network has been extracted (`klt extract` synthesises the substrate
as one node, `GND|VGND`, with no resistance). **Assumed**, and stated as
assumptions below: every number in the Decision.

## Decision

1. **Package model, per bonded supply terminal: one gold bond wire, 25 µm
   diameter, 2 mm long, modelled as series R + L between an ideal board-side
   source and the die-side node.**
   - `L = (µ0·l / 2π)·(ln(2l/r) − 3/4) ≈ 2.01 nH`. This is the low-frequency
     self-inductance of an isolated straight round wire.
   - `R = ρ·l / A ≈ 0.099 Ω`. This is the DC value, with bulk Au ρ =
     2.44×10⁻⁸ Ω·m.
   - The geometry is an assumption: 25 µm is the common fine-pitch ball-bond
     gauge, and 2 mm is a representative die-edge-to-lead span for a small
     die. Both values come from geometry and bulk material constants alone,
     not from any package datasheet or any other party's design.
2. **Substrate stand-in: one lumped resistor `R_sub` between the analog ground
   (`GND`) and the digital ground (`VGND`) on die, run at two bracketing
   values, 10 Ω and 1 kΩ.** 10 Ω is the low end of DR-012's own "10s of ohms".
   1 kΩ is two decades above it. Neither value is claimed to be physical. A
   conclusion is only drawn from this model if it holds at **both** ends.
3. **Everything else stays ideal, and the records must say so:** the board
   (no board impedance, no board decoupling), the references and inputs
   (`VREFP`/`VREFN`/`VCM`/`VINP`/`VINN`/`CLK`/`RST_B`), and mutual
   inductance between wires (not modelled). **No on-die decoupling is
   modelled**, because none exists in this design (DR-010's open item).
4. **Scope.** These values are **testbench stimulus**. They are not a claim
   about which package the block ships in, and no result is graded against
   them as a threshold. When a real package is chosen, with a real lead frame
   and board, that choice is a new decision with its own record. That record
   supersedes this one, and the campaigns citing this one must be re-run with
   the new numbers.

## Alternatives considered

- **State the values in the campaign README only, with no DR**, following
  `sim/vcm-drive-budget/`'s assumed `VCM` source resistance. This was not
  chosen. #378 explicitly asks for a package-style assumption to be recorded
  as a decision, and a later supply campaign should cite one record rather
  than copy a README's numbers. The cost of not taking this option is one
  more record to supersede when a package is chosen.
- **Take R/L from a published package datasheet.** Not chosen. It would tie
  this clean-room block's evidence to a third party's product, and it would
  imply a package choice that nobody has made. A first-principles wire gives
  the same order of magnitude with no outside dependency. The cost is that
  lead-frame and board inductance, which a real package adds on top, are
  missing.
- **Sweep L over a wide range, for example 0.5–10 nH.** Not chosen for the
  first record. Each point is a ~6 µs whole-ADC transient, and 8 arms × 9 PVT
  points already make 73 runs. The single value sits at the physically
  small end, and the omissions are stated. A later campaign can widen the
  sweep by citing this record.
- **Extract a real substrate network.** Not available. No substrate-resistance
  extraction exists in this repo's flow. The bracket stands in for it and
  says so.

## Spec lines affected

**None.** No row of `spec/target-spec.md` changes, and none is added. This
record fixes only the stimulus of `sim/ground-return-impedance/`
(`R_PKG_OHM`, `L_PKG_H` and `R_SUB_OHM` in `run_ground_return.py`, which
derive these values rather than hard-coding them).

## Consequences

- DR-012's "the impedance argument is unmeasured" item can be retired by
  citation to a committed record, **scoped to this model**. The retirement
  reads "measured under DR-015's stated model", not "measured on a package".
- The model is optimistic in one direction and pessimistic in another. Using
  one isolated wire with no lead frame or board *understates* inductance.
  Using the DC resistance and no decoupling anywhere *under-damps* the LC, so
  ringing is worse than a damped real supply would show. A reader should not
  read a clean result as margin against a real package's larger L.
- A future package decision must supersede this record, and every campaign
  citing it must be re-run. That is the intended cost of writing the
  assumption down.

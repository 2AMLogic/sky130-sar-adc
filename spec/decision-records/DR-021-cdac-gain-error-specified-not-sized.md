# DR-021: Specify the CDAC's systematic gain error as its own spec row. Neither sizing lever can remove it

- **Status**: proposed. Ratification is via the operator's approval of the PR
  that resolves #269's decision step, under the canary spec/DR
  ratification-via-PR standing policy (2AMLogic/2am#357) and the two-key route
  2am#1056 confirms for new or amended DRs. This record **proposes** a spec
  row. It does not edit `spec/target-spec.md`. See "Spec lines affected".
- **Date**: 2026-10-03
- **Decided by**: Builder agent, issue #269 (scope per the issue's
  "Revision 2026-09-14 (operator lane)": draft the DR, recommend one option,
  do not implement it)
- **Supersedes**: none. This is the first record on a gain-error row. It closes
  the "A gain-error spec row" gap that DR-003 Item 3 flagged, for the
  systematic half only (see "Open items"). It also answers DR-009's first
  Open item. DR-003 and DR-009 stand unedited.
- **Superseded by**: (none while this record stands)
- **Related**: #269 (this decision), #263 / [DR-009](DR-009-comparator-output-load-balance-and-half-lsb-offset.md)
  (the half-LSB offset cell, a fixed part of the gain error, and the record
  whose Open item this answers), [DR-003](DR-003-numeric-spec-derivation.md)
  Item 3 (the ratified `C_u` and its `1.42 LSB` 3σ mismatch gain error),
  [DR-004 (sampling front end)](DR-004-sampling-frontend-sizing.md) (the
  `Csamp_x` cap that DR-004 calls "inert"; it loads the top plate here),
  [DR-004 (comparator)](DR-004-comparator-topology-and-noise-budget.md),
  [DR-005](DR-005-cdac-array-design.md), [DR-008](DR-008-cdac-top-level-switching-polarity.md),
  [DR-018](DR-018-midscale-code-metastable-msb.md) (owns the mid-scale code),
  [DR-019](DR-019-cdac-unit-cap-grid-legal-plate-resize.md), [DR-020](DR-020-comparator-offset-and-dead-band-spec-rows.md),
  #267 (the near-full-scale common-mode saturation that #265 confirmed),
  **evidence**: `sim/full-conversion-transient/records/20260912-011519-9aaf1ca.md`
  (the decision-margin trace that every gain number below comes from),
  `sim/full-conversion-transient/records/20261001-105439-c324f80.md` (latest
  9-corner campaign at the DR-019 `C_u`), **port parity**:
  `2AMLogic/gf180-sar-adc` DR-0012 (gain-error split, systematic vs mismatch),
  DR-0014 (bottom-plate sampling), DR-0019 (unit-cap resize for gain-error margin).

## Context

**The mechanism (re-derived; it agrees with #269).** On a top-plate-sampled
CDAC the sampled input lands on the top plate undivided. Each later DAC step
is divided by *everything* on that node:

```
per-unit DAC step = V_REF * C_u / (C_array_side + C_par)      C_array_side = 512 * C_u (DR-005)
gain g            = 512 * C_u / (512 * C_u + C_par)           gain error eps = 1 - g
```

**The measured gain.** I re-derived it from the committed trace and did not
copy it from the issue. `20260912-011519-9aaf1ca.md` records the comparator's
own differential input at every bit-trial instant of the `-0.25`, `+0.00` and
`+0.25 * V_REF` conversions, at `tt_27c_1.80v` and `tt_27c_1.62v`. Trial `k`
moves the residual by `2^k` units. That gives two independent ways to read
`g`:

1. **The bit-8 symmetric pair.** DR-009's half-LSB cell switches `Choff_n` on
   the `PH_B9 -> PH_B8` edge (`HALF_LSB_EN = BUSY AND NOT PH_B9`), the same
   edge as the bit-8 trial. Every bit-8 delta therefore carries the half-LSB
   step `s` with a fixed sign. The trial direction itself depends on `DOUT9`.
   - `+0.00` conversion: `Delta = +894.536 mV = +256*u*g + s`
   - `+0.25` conversion: `Delta = -891.071 mV = -256*u*g + s`
   - The two equations give `256*u*g = 892.80 mV`, so **`g = 0.99200`**.
     They also give `s = +1.73 mV`, which matches a half LSB scaled by `g`
     (`1.758 * 0.992 = 1.744 mV`).
   - At `1.62 V`: `256*u*g = 803.47 mV` against an ideal `810.00 mV`, so
     **`g = 0.99194`**, with `s = 1.55 mV`.
2. **The bits 7..4 steps**, which carry no half-LSB term. All 12 steps at each
   corner fall in `0.9917–0.9923`, while the top-plate common mode moves from
   `565` to `871 mV` (at `1.8 V`).

| quantity | `tt_27c_1.80v` | `tt_27c_1.62v` |
|---|---|---|
| gain `g` (bit-8 pair) | `0.99200` | `0.99194` |
| `eps = 1 - g` | **`0.80 %`** | **`0.81 %`** |
| gain error, span-referred (`eps * 2^N`) | **`8.2 LSB`** | **`8.3 LSB`** |
| ... at `+-0.25 * V_REF` (`eps * 128 LSB`) | `1.0 LSB` | `1.0 LSB` |
| ... at `+-0.78 * V_REF` (`eps * 399 LSB`) | `3.2 LSB` | `3.2 LSB` |
| `C_par = 512 * (1/g - 1)` | `4.13 C_u` (`35.7 fF` at the trace's `C_u = 8.654 fF`) | `4.13 C_u` |

**This trace corrects four details in #269's text.**

- The issue cites the corner-campaign record `20260912-002315-9aaf1ca.md`
  for the two numbers. They are actually in the trace record named above.
- `894.5 mV` vs `900.0 mV` overstates `g` (`0.9939`), because that delta
  includes the half-LSB step. Removing it gives `0.9920`.
- I could not reproduce `+3.73 mV` / `+1.06 LSB` to the digit. Decomposing
  the `+0.25` bit-7 residual (`+6.310 mV` measured vs `+2.79 mV` for `g = 1`
  with the same sampled value and `s`) gives **`+3.5 mV` (`+1.0 LSB`)**. The
  two agree to within `0.07 LSB`.
- `C_u` is `8.65 fF`, not "~7 fF". DR-003 Item 3 includes the perimeter term.
  So `C_par` is about `36 fF`, not about `30 fF`.

The latest campaign (`20261001-105439-c324f80.md`, at the DR-019 `C_u`)
fits the gain exactly. `+-0.25 * V_REF` reads `641` / `383` at 9/9 corners,
which is `round(+-128/0.992) = +-129`. The mid-scale `511` is DR-018's
metastable MSB, not gain. The `+-0.78` failures are #267's saturation. Gain
adds only about 3 LSB of them.

**What makes up `C_par`.** Only the total is measured. The split below is an
**estimate** from the netlist (`design/sar_adc_top.spice`) and the PDK's
`tt` model parameters. It assumes the comparator is in reset with its tail
off, which is the state at every traced instant, and about 0.9 V of reverse
bias on the junctions. Per side:

| contributor | basis | `C_u` equivalents |
|---|---|---|
| `Choff_x` (DR-009 half-LSB cell, and its matched dummy on the other side) | one unit cap, exact by design | **`1.00`** |
| `Csamp_x` in series with node `BPREF_x` | `BPREF_x` floats after sampling. The `4.43 pF` `Csamp_x` couples it to `TOP_x`, so `TOP_x` sees `BPREF_x`'s own load: junction and overlap capacitance of the two `W = 16 um` `Cmswn`/`Cmswp` devices (`~18–24 fF`) | **`~2.1–2.8`** |
| sampling switch `Msw_x` (`W = 2 um`) | junction + overlap | `~0.2` |
| comparator input device (`W = 4 um`, `L = 0.5 um`) | overlap (`~1 fF`) up to full-inversion gate (`~18 fF`). The measured total puts it near the low end | `~0.1–2.2` (inferred `~0.13–0.83`) |
| **measured total** | | **`4.13`** |

The estimate overturns two earlier attributions:

- The comparator is **not** shown to dominate, contrary to #269 and DR-009.
- DR-004 (sampling front end) calls `Csamp_x` "inert". It is inert only if
  `BPREF_x` has zero capacitance. It does not, so it is likely the largest
  device-level contributor.

**One number does not depend on that estimate.** `Choff_x` is one unit cap,
and DR-009 requires it to track `C_u`. It contributes
`eps = 1/513 = 0.19 % = 2.0 LSB` span-referred. That holds at any `C_u` and
for any comparator size.

## Decision

**Adopt option 3 of #269: specify the systematic gain error as its own spec
row. Do not try to remove it by resizing the unit cap (option 1) or the
comparator input pair (option 2).** Specifically:

1. **Proposed new row**, structure ported from gf180-sar-adc DR-0012 (the
   value is not ported; see 2):

   | Parameter | Target | Status | Binding condition / note |
   |---|---|---|---|
   | Gain error, systematic | `<= 1.42 LSB` span-referred (`<= 0.139 %` of full scale), untrimmed, excluding `V_REF` error | DRAFT (DR-021 candidate) | full ratified PVT corner set **plus the MiM r+c corners**, zero mismatch. Measured `8.2–8.3 LSB` at the two traced corners (schematic), about `5.8x` over. Recorded, not relaxed. |

2. **The candidate value is derived, not invented and not fitted to the
   measurement.** It uses gf180 DR-0012's own method:
   - The deterministic term gets an *equal share* with the mismatch term that
     the ratified unit cap already commits the block to. Looser would let an
     unnamed mechanism dominate the headline. Tighter would be unearned.
   - Here, the mismatch term is DR-003 Item 3's ratified-`C_u` figure:
     `3 * 32 * sigma_u = 1.42 LSB`.
   - gf180's `0.5 LSB` is that same method applied to gf180's larger `C_u`.
     `target-spec.md`'s "Non-goals" says sky130 numbers are re-derived, not
     ported, so the number diverges while the method carries.
   - Meeting the candidate would also keep the gain-induced error at every
     input in `sim/full-conversion-transient/`'s schedule within `0.55 LSB`
     (`0.139 % * 399 LSB`). That is the property #269's "`< 0.1 %`"
     acceptance line was reaching for.

3. **Restate the campaign's acceptance criterion by splitting it, not by
   loosening it.** `sim/full-conversion-transient/` keeps its absolute-code
   `+-1 LSB` verdict exactly as it is (still informational). It also reports,
   per corner:
   - (a) the extracted gain `g`, using the bit-8 symmetric-pair method above,
     against the new row;
   - (b) each input's code error after removing `g` and offset, against
     `+-1 LSB`.

   No existing verdict is dropped or widened. The split only names which
   mechanism caused a miss.

This record **does not implement anything.** No schematic, sizing, testbench
or `target-spec.md` change is made. Closing the measured `5.8x` miss is a
separate decision (see "Open items").

## Alternatives considered

- **Option 1: grow `C_u`.** Rejected because it cannot reach the row, at any
  size:
  - `Choff_x` scales with `C_u` and alone exceeds the candidate
    (`2.0 > 1.42 LSB`).
  - Growing `C_u` also tightens the candidate, because `sigma_u` falls as
    `1/sqrt(area)`.
  - Doubling `C_u` cuts the device-level part in half and `eps` only to about
    `0.50 %` (`5.1 LSB`). The cost is about 2x the array area, 2x the reference
    charge per conversion (`I(VREFP)` is about `6.5 uA` today), and 2x the
    sampling time constant. That would use up the roughly 2x margin of
    `sim/sampling-acquisition-settling/`'s binding corner.
  - Reaching even `0.1 %` on the device-level part needs about `6x C_u`.
    Without a gain-error row, this option buys area for a target nobody has
    written down.
- **Option 2: shrink the comparator input pair.** Rejected:
  - Its share is the smallest and least certain line in the table (inferred
    `~0.13–0.83 C_u`). Removing it completely still leaves
    `eps >= ~0.6 %` (`~6 LSB`).
  - The cost is concrete. Random offset `sigma` already measures `97 mV` at
    `W = 4 um` (DR-020). Pelgrom scaling doubles it if the area shrinks 4x.
    DR-004's `<= 1.0148 mV rms` noise budget would also need re-verifying.
- **Options 1 + 2 together.** Rejected for the same floor: `Choff_x` and the
  `Csamp_x`/`BPREF_x` path are untouched by both.
- **Restate the campaign criterion with no row.** This would read the
  `+-0.25` codes as passing "after gain correction" with no bound on the gain.
  Rejected: it is the silent loosening CLAUDE.md forbids. A gain error with
  no bound is unbounded.
- **Write the row at the measured level (e.g. `<= 10 LSB`).** Rejected. A row
  sized to the current measurement is not a spec, and this would be a
  relax-after-measured-FAIL. If the operator decides the `5.8x` miss should
  not be closed, the right path is a superseding DR that states the looser
  value as a ratified departure. Editing this candidate to fit is not.
- **Adopt gf180's `0.5 LSB` verbatim** (the DR-011 style of sibling adoption).
  Rejected: it would port a number that comes from gf180's `C_u`. Its
  derivation does carry over, and point 2 of the Decision applies it.
- **Bottom-plate sampling** (gf180 DR-0014: it removes the top-plate divider
  from the gain entirely). Not chosen as *this* decision:
  - It changes the architecture (the DRAFT Architecture row, DR-004
    sampling, DR-005, DR-008), which is far outside #269's sizing-or-spec
    question.
  - gf180's main reason, an INL/SFDR bow from a voltage-dependent `C_par`
    (`0.85 pp` divider variation there), is **not evidenced** here. The
    traced divider varies by `<= 0.06 pp` across a `~300 mV` common-mode
    range and by `0.01 pp` between supplies, so it behaves as a near-pure
    scale factor.
  - It stays a candidate for closing the row's miss (see "Open items").

## Spec lines affected

- `spec/target-spec.md` "Target table": **proposed new row**, "Gain error,
  systematic", as in Decision item 1. This record does not add it. The row
  is added DRAFT by the change that ratifies this record.
- `spec/target-spec.md` "Not ratified by this record", "A gain-error spec row"
  bullet: answered for the **systematic** half on ratification. The mismatch
  half remains open (see "Open items").
- **Port parity:**
  - Row structure: carried from gf180-sar-adc DR-0012.
  - Value: re-derived by the same method (`1.42` vs gf180's `0.5 LSB`, because
    DR-003 ratified a smaller `C_u`).
  - Architecture: this repo's DRAFT row reads "top-plate sampling, carried
    from gf180-sar-adc", but gf180 has since adopted bottom-plate sampling
    (DR-0014). That divergence is recorded here and not resolved.

## Consequences

- **The block now has a gain-error row that it fails by about `5.8x`, and
  that failure is visible on purpose.** Before this record, the error showed
  up as a vague `+-1 LSB` absolute-code miss. After it, the error has a
  name, a number, and a gap.
- **No sizing change can close the gap.** Any fix has to change the
  structure on the top plate (see "Open items"). This is the main bad
  consequence, and the main thing the operator is asked to look at.
- `sim/full-conversion-transient/` gains a per-corner gain extraction and a
  corrected-code column. Today's trace covers only 2 of the 9 corners. The
  row is a capacitance ratio, so its binding condition must also sweep the
  r+c corners, which the ratified `tt/ss/ff/sf/fs` libraries do not (every
  one of them loads `res_typical__cap_typical`). At `cap_low`, `C_u` falls to
  about `6.65 fF` and the device-level part of `eps` rises by about `1.3x`,
  to about `1.0 %`.
- No existing record is invalidated. No sub-block re-derivation is triggered
  (`sim/cdac-array-transfer/`, `sim/comparator-decision/` and
  `sim/sampling-acquisition-settling/` are untouched), because nothing is
  resized.
- `sim/` evidence is unchanged. This record minted no new record and ran no
  simulation. Every number above comes from the two committed records and
  the PDK model files.

## Open items

Each item is to be filed on ratification, since its shape depends on that
ruling:

1. **Measure the composition of `C_par`.** A C(V) extraction on `TOP_x` in
   the reset/hold state, per corner, including the r+c corners. gf180 does
   this in `sim/top-plate-cpar/`. It replaces the estimate table above, and
   it decides which closure path in item 2 is worth taking.
2. **Close or supersede the miss.** A later DR chooses among:
   - (a) moving the half-LSB offset into the existing termination cap
     (DR-009's own named alternative, about `-1 C_u`/side);
   - (b) removing the inert `Csamp_x`/`Cmsw*` network (DR-004 sampling's open
     item, estimated about `-2.1–2.8 C_u`, which also halves the sampling
     load);
   - (c) bottom-plate sampling (gf180 DR-0014);
   - (d) digital gain correction;
   - or a superseding DR that ratifies a looser value as a recorded departure.

   (a) and (b) together leave about `0.3–1.0 C_u` (`~0.7–2.1 LSB`). So the
   row may be reachable *without* an architecture change, but only item 1's
   measurement can say so.
3. **Gain error, mismatch** (the other half of gf180's split). DR-003 Item 3's
   analytic `1.42 LSB` at 3σ has no row and no Monte Carlo check. A user
   measures the sum of the two halves, so the published total waits on it.
4. **Implement Decision item 3** (gain extraction plus corrected-code
   reporting across all 9 corners) once this record is ratified.

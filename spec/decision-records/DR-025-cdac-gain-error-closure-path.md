# DR-025: Close the CDAC gain-error miss by removing the inert sampling network and folding the half-LSB cap into the termination cap

- **Status**: proposed. This record **proposes** a closure path. It implements
  nothing and edits no spec row. Ratification is the operator's approval of
  the PR that carries it, on the same two-key route as DR-022 (EE and market
  reviews posted on the PR first).
- **Date**: 2026-11-01
- **Decided by**: Builder agent, issue #755 (scope: choose among DR-022 Open
  item 2's options; decision only)
- **Supersedes**: none. It answers [DR-022](DR-022-cdac-gain-error-specified-not-sized.md)
  Open item 2 and leaves DR-022 standing, unedited.
- **Superseded by**: (none while this record stands)
- **Related**: #755 (this decision), #754 / PR #761 (the measurement),
  [DR-022](DR-022-cdac-gain-error-specified-not-sized.md),
  [DR-009](DR-009-comparator-output-load-balance-and-half-lsb-offset.md)
  (the half-LSB cell and its named termination-cap alternative),
  [DR-004 (sampling front end)](DR-004-sampling-frontend-sizing.md) (the
  `Csamp_x` "inert" resolution and its open item), [DR-005](DR-005-cdac-array-design.md),
  [DR-003](DR-003-numeric-spec-derivation.md) Item 3.
  **Evidence**: `sim/top-plate-cpar/records/20261101-183325-60421e38.md`.
  **Port parity**: `2AMLogic/gf180-sar-adc` DR-0012, DR-0014, DR-0019.

## Context

DR-022 proposes a DRAFT systematic gain-error row, `<= 1.42 LSB`
span-referred, and records a miss of `8.2–8.3 LSB` (about `5.8x`) at two
traced corners. It showed that neither unit-cap nor comparator resizing can
close the miss, and left the closure to a later DR. DR-022 split `C_par` by
estimate. #754 has since **measured** it.

**Verified facts, all from the one #754 record** (13/13 corners, status
COMPLETE; `C_par = C_node - 512*C_u`; testbench-only leave-one-out):

- `C_par` is `3.43` (`hh`/`lh`) to `4.66` (`ll`/`hl`) `C_u`, mean over bias.
  It is `3.962 C_u` (33.3 fF) at `tt_27c_1.80v`. The measured `tt` total is
  `0.17–0.18 C_u` below DR-022's `4.13`/`4.18`.
- The four loads below account for all of it: with all four deleted the
  remainder is `0.000 C_u` and the non-additivity residual is under `0.001`.
- Per-load, in `C_u` of each corner (range over the 11 distinct corners):
  `Choff_x` `1.000` (exact by design); `Csamp_x`/`BPREF_x` branch
  `1.816–2.737` (`tt` `2.216`); `Msw_x` `0.143–0.216` (`tt` `0.175`);
  comparator input pair `0.467–0.705` (`tt` `0.570`).
- Bias dependence is small: `C_par` moves `<= 0.16 C_u` over the traced
  565–871 mV range at every corner (largest: `tt_125c`, `4.021..4.175`). `P` and `N` sides are identical to the
  printed digits.

The cap corners `ll`/`hh`/`hl`/`lh` are the r+c-style corners. `ll` and `hl`
give identical numbers, as do `hh` and `lh`. In this deck only `C_u` moves
between them, so the four rows are two distinct data points, not four.

**Caveats carried from the record.** (1) It was produced from a dirty tree
(`feature/issue-754`, git `60421e38`). (2) The executing workers used PDK
`c6d73a35` and ngspice-46, while the submitting host used `f6eeac7d` and
ngspice-42. So no comparison with a locally run record, including DR-022's
`full-conversion-transient` numbers, is controlled for versions. (3) Only
the as-committed deck was measured. Every "after" number below is
subtraction from that record, not a simulation of a changed circuit.

**Reach arithmetic (derived here, not copied).** Span-referred gain error is
`eps * 2^N` with `eps = C_par / (512 C_u + C_par)` and `2^N = 1024`, which
reproduces DR-022's `8.2 LSB` from `4.13 C_u`. The `1.42 LSB` candidate
therefore needs `C_par <= 0.711 C_u`. For each option, "after" is the
measured `C_par` minus the measured load(s) it deletes:

| corner | base `C_par` (LSB) | (a) | (b) | (a)+(b) |
|---|---|---|---|---|
| `tt_27c_1.80v` | 3.962 (7.86) | 2.962 (5.89) | 1.571 (3.13) | **0.571 (1.14)** |
| `ss_27c_1.80v` | 4.129 (8.19) | 3.129 (6.22) | 1.564 (3.12) | 0.564 (1.13) |
| `ff_27c_1.80v` | 3.775 (7.49) | 2.775 (5.52) | 1.577 (3.14) | 0.577 (1.15) |
| `sf_27c_1.80v` | 3.786 (7.52) | 2.786 (5.54) | 1.565 (3.12) | 0.565 (1.13) |
| `fs_27c_1.80v` | 4.116 (8.17) | 3.116 (6.19) | 1.575 (3.14) | 0.575 (1.15) |
| `tt_-40c_1.80v` | 3.934 (7.81) | 2.934 (5.83) | 1.577 (3.14) | 0.577 (1.15) |
| `tt_125c_1.80v` | 4.099 (8.13) | 3.099 (6.16) | 1.544 (3.08) | 0.544 (1.09) |
| `tt_27c_1.62v` | 3.998 (7.93) | 2.998 (5.96) | 1.571 (3.13) | 0.571 (1.14) |
| `tt_27c_1.98v` | 3.930 (7.80) | 2.930 (5.83) | 1.570 (3.13) | 0.570 (1.14) |
| `ll`/`hl` (cap low) | 4.658 (9.23) | 3.658 (7.26) | 1.705 (3.40) | **0.705 (1.41)** |
| `hh`/`lh` (cap high) | 3.427 (6.81) | 2.427 (4.83) | 1.468 (2.93) | 0.468 (0.94) |

(Entries are `C_par` in `C_u`, then span-referred LSB in brackets; where
`(a)` or `(b)` is chosen alone the other loads stay.)

Two corrections to the issue/DR-022 wording follow from this table:

- Deleting `Csamp_x` and `Msw_x` alone (option b) leaves `1.47–1.71 C_u`
  (`Choff_x` plus the comparator), as the re-curation noted. That is
  `2.9–3.4 LSB`, still `2x` over the row.
- DR-022's "(a)+(b) leave about `0.3–1.0 C_u`" is **not reused**. The
  recomputed residual for (a)+(b) is the comparator input pair alone,
  `0.47–0.71 C_u`, which happens to lie inside DR-022's range. That
  agreement is a coincidence of two estimates, not a confirmation: DR-022's
  `0.3–1.0` was never traced.

## Decision

**Propose (a) + (b) as the closure path: remove the inert
`Csamp_x`/`Cmsw*` network, and fold DR-009's half-LSB offset into the
existing per-side termination cap. Do not ratify a looser value now, and do
not choose (c) or (d) now.** Specifically:

1. **(b) is the first step and carries most of the benefit.** Per corner it
   removes `1.96–2.96 C_u` (`tt` `2.39`), about `3.9–5.8 LSB` of the `6.8–9.2
   LSB` base. It also halves the sampling-path load, which DR-004
   (sampling) already named as an open cost. Alone it does not reach the row
   (`2.9–3.4 LSB`, `2x` over).
2. **(a) is the second step.** It removes `1.000 C_u` (about `2 LSB`), and
   with (b) takes `tt` to `0.571 C_u` (`1.14 LSB`) against `1.42`. DR-022
   already showed that `Choff_x` alone is `2.0 LSB`, more than the row, so
   no combination that keeps it can meet the row.
3. **The combination does not demonstrably meet the row at the cap-low
   corners.** At `ll`/`hl`, (a)+(b) gives `0.705 C_u`, `1.41 LSB` mean over
   bias, against a limit of `0.711 C_u` / `1.42 LSB`. The margin is `0.01
   LSB`. The record's own bias spread of the total (`+-0.05 C_u`, about
   `+-0.1 LSB`) is ten times that, and the per-load bias dependence of the
   comparator pair alone was not measured. So the honest statement is
   "reaches 0.9–1.15 LSB at nine corners and `hh`/`lh`, and is at the limit
   at `ll`/`hl`", not "meets the row".
4. **Gate before any ratified claim.** The (a)+(b) schematic is to be
   measured with the same `sim/top-plate-cpar/` method before anyone writes
   "meets". That measurement also has to include the parasitics that making
   the termination cap switchable adds to the top plate, which this record
   cannot see (the record measured only the four existing loads).
5. **Fallbacks, in order, if that measurement fails the row:** (c)
   bottom-plate sampling (below), then a superseding DR ratifying a looser
   value as a recorded departure. Any looser value must be derived then from
   the measured post-change `C_par` and recorded as a departure. The DRAFT
   row in `spec/target-spec.md` is not edited by this record or to fit.

This record **implements nothing.** No schematic, sizing, testbench or
`target-spec.md` change is made, and no simulation was run to write it.
Every number is read or subtracted from the one committed record above.

## Alternatives considered

- **(a) alone.** Rejected as a stopping point: it leaves `2.4–3.7 C_u`
  (`4.8–7.3 LSB`), over `3x` the row, at every corner.
- **(b) alone.** Rejected as a stopping point: `2.9–3.4 LSB`, `2x` over, and
  `Choff_x` by itself is `2.0 LSB` span-referred. Kept as step 1 because it
  is the largest single lever and is independent of the DR-009 rework.
- **(c) bottom-plate sampling (gf180 DR-0014).** Not chosen now. It removes
  the top-plate divider from the gain by construction, so it is the
  strongest closure, but it is an architecture change (the DRAFT
  architecture row, DR-004 sampling, DR-005, DR-008) and adds a switch leg to
  every cell. gf180's motivation, an INL/SFDR bow from a voltage-dependent
  `C_par`, is not evidenced here: #754 measures `<= 0.16 C_u` of variation
  over the traced range, about `0.3 LSB` of span-referred gain, and DR-022
  measured the divider as a near-pure scale factor. Kept as the first
  fallback. Cost of not choosing it: if (a)+(b) lands at `ll`/`hl` over
  `1.42`, this decision is reopened and a second schematic round is spent.
- **(d) digital gain correction.** Rejected as a closure of *this* row. The
  candidate row is "untrimmed", and a fixed correction cannot cover the
  corner spread: base gain error spans `6.8–9.2 LSB` across the measured
  corners, `+-1.2 LSB` about the middle, itself near the `1.42` budget. A
  per-part trim redefines the row rather than meeting it, and the
  correction moves the problem into a digital block and a calibration
  procedure that nothing in `spec/` defines. It remains legitimate
  *in addition to* a hardware fix, and would be a separate decision.
- **Superseding DR ratifying a looser value now.** Rejected: nothing yet
  shows the hardware route fails, and a looser value derived from today's
  `3.4–4.7 C_u` would be the relax-after-measured-FAIL that CLAUDE.md
  forbids. It becomes the right answer only if the step 4 measurement fails,
  and then must be derived from that measurement.

## Spec lines affected

- `spec/target-spec.md` "Gain error, systematic" (DRAFT, DR-022 candidate):
  **no edit.** Its note "Measured `8.2–8.3 LSB` ... other corners unmeasured"
  is now stale for the composition (the 13-corner `C_par` is measured), but
  updating a DRAFT row's note is for the ratification-vehicle PR, not this
  record.
- **Port parity.** gf180 DR-0012 (systematic vs mismatch split): row
  structure already carried by DR-022; unchanged here. gf180 DR-0014
  (bottom-plate sampling): gf180 adopted it as its closure, this record
  chooses a different first path (a)+(b) on sky130 and keeps (c) as the
  fallback. **Divergence recorded**: sky130 keeps top-plate sampling for now,
  because the measured `C_par` here includes a removable `~2.4 C_u` inert
  branch whereas gf180's DR-0014 argument rests on a voltage-dependent
  divider that #754 does not show on sky130. gf180 DR-0019 (unit-cap resize
  for gain-error margin): the mismatch-half lever. Not applicable to the
  systematic half here (DR-022: `Choff_x` scales with `C_u`); sky130's
  `C_u` stays as DR-019 set it.

## Consequences

- **Files the closure will touch (so the follow-up issue is sized right).**
  Option (a) deletes `XChoff_p`/`XChoff_n` from `design/sar_adc_top.spice`
  and makes the termination cap switchable. That:
  - changes `design/cdac/cdac_array.sch`'s port list, which DR-009
    recorded as invalidating `sim/cdac-array-transfer/`'s testbench and
    record and re-opening DR-005;
  - retires the `layout/halflsb-offset/` flow and its schematic-parity gate.
    `sim/tests/test_halflsb_offset_schematic_parity.py` pins that gate to
    the `Choff` cell's device table in `design/sar_adc_top.spice`, so the
    test must be removed or re-pointed in the same change. It cannot just be
    left red or xfailed.
  Option (b) removes `Csamp_p`/`Csamp_n`/`BPREF_x`/`Cmswn`/`Cmswp`, which
  re-opens DR-004 (sampling front end)'s `Sa`/`Sd`/`Cboot` verification
  against a smaller load, the very reason that record left them in.
- **Cost of (a)+(b), stated:** two sub-block re-verifications
  (`sim/cdac-array-transfer/`, `sim/sampling-*`), one layout-flow retirement,
  and a DR-009 half-LSB re-verification, in exchange for roughly `6–8x` less
  gain error at the nine non-cap-corner points. There is no sizing-only way to get that.
- **Probable outcome is "at the limit", not "pass", at `ll`/`hl`.** The
  operator should read step 3 as a real risk, not a footnote.
- `sim/` evidence is unchanged and no record is minted. Nothing is
  invalidated by this record itself.

## Open items

1. **File the implementation issues on ratification**, one per step: (b)
   remove the inert network and re-verify DR-004 sampling; (a) switchable
   termination cap, with the `sim/cdac-array-transfer/` and layout-parity
   consequences above. Their order is the Decision's order.
2. **Re-measure `C_par` on the changed schematic** with
   `sim/top-plate-cpar/`, all 13 corners, from a clean tree and with a
   controlled PDK/simulator version, and include per-load bias dependence
   at `ll`/`hl`. This decides the step 5 fallback.
3. **Gain error, mismatch half** (DR-022 Open item 3) and **campaign
   reporting** (DR-022 Open item 4) are unchanged and out of scope.
4. **Rebase note.** Open PR #758 edits DR-022's status and Open items.
   This record cites DR-022 Open item 2 by number and does not depend on
   #758's wording; re-check the reference after #758 merges.

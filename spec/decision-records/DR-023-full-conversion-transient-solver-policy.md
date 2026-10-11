# DR-023: Full-conversion transients integrate with an explicit solver policy, `reltol=1e-4` + Gear, instead of ngspice's defaults

- **Status**: proposed. Ratification is via the operator's approval of the PR
  resolving #637, per the canary ratification-via-PR standing policy
  (2AMLogic/2am#357) that DR-003 / DR-011 / DR-019 / DR-020 / DR-021 cite.
  This record is a **simulation-harness** decision. It edits no row of
  `spec/target-spec.md` and changes no target, threshold or tolerance.
- **Date**: 2026-10-11
- **Decided by**: Builder agent, issue #637 (follow-up from #621 / PR #636)
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #621 (the conversion-9 root cause), #637 (this decision);
  `sim/full-conversion-transient/run_conversion.py` (`SOLVER_PROFILES`,
  `REFERENCE_SOLVER_PROFILE`, `--solver-profile`, `--solver-audit`);
  evidence consumed, all under `sim/full-conversion-transient/records/`:
  `20261011-022915-877794b` (coherent-sine, ngspice defaults),
  `20261011-023419-877794b` (coherent-sine, `reltol=1e-4 method=gear`),
  `20261011-064924-ad4bfff` (coherent-sine, `reltol=1e-4` only),
  `20261011-064408-ad4bfff` (coherent-sine, `method=gear` only),
  `20261011-064547-a6dcdd7` (DC baseline-corner solver audit, all four
  profiles), and `20261001-105439-c324f80` (`records/LATEST`, the DC corner
  campaign the audit re-checks).

## Context

Until this record, every full-conversion transient ran on ngspice's
transient defaults (`reltol=1e-3`, trapezoidal integration). Nobody chose
them; they were simply what the deck inherited. Issue #621 showed that they
can produce a false converter result. In the coherent-sine capture,
conversion 9 returned code 960 against an ideal 522 (+438 LSB). The
switching trace shows four already-decided bit registers flipping 0 -> 1
with no clock edge, during the comparator's regeneration
(`20261011-022915-877794b`). Adding `.options reltol=1e-4 method=gear`, with
the same DUT, stimulus, ngspice-47 and PDK pin, removes the event
(`20261011-023419-877794b`). That control changed two settings at once.
Every other transient record in the experiment also ran on the defaults,
including the DC corner campaign that `records/LATEST` names.

**Verified** (on the pinned toolchain: ngspice-47, sky130A @
`c6d73a35f524070e85faff4a6a9eef49553ebc2b`, DUT netlist sha256 `3a519b41...`):

1. **Either setting alone removes the artefact.** The two single-setting
   coherent-sine controls (`reltol=1e-4` only, `20261011-064924-ad4bfff`; Gear
   only, `20261011-064408-ad4bfff`) return the same 32-code stream as the
   combined control, code for code. Conversion 9 is 521 (ideal 522). There
   are no UNSCHEDULED transitions in conversion 9, TOP_P stays inside the
   rails, and there are 0 outliers above 8 LSB (max |error| 2 LSB). SNDR is
   52.00 dB. The default stream differs from all three in conversion 9 only.
2. **No recorded DC failure mode moves at the baseline corner.**
   `20261011-064547-a6dcdd7` runs the DC fragment at tt/27C/1.8V under all four
   profiles. The `ngspice-default` run reproduces `records/LATEST`'s
   `tt_27c_1.80v` row exactly (codes 214 / 383 / 511 / 641 / 1023, 27.986 uW;
   LATEST used ngspice-46, the audit ngspice-47). Under every control, the
   same three mid-scale inputs pass and the same two near-full-scale inputs
   fail (DR-021's issue). Phase structure is 5/5 everywhere, and no
   register transition is UNSCHEDULED. Two values do move:
   * **Total power falls 1.9-2.8 %** (27.986 -> 27.197 uW under `reltol-gear`).
     Most of the drop is the digital rail (`I(VPWR)` -5 to -6 %). The two
     `reltol=1e-4` profiles still differ from each other by 0.9 %. The DRAFT
     Power figure therefore carries about a 3 % integration-setting
     uncertainty that no record stated before.
   * Under both `reltol=1e-4` profiles, TOP_N in conversion 3 (the 0.00
     input) dips below -0.2 V for a moment, 3.3 ns after the phase-2 edge. The
     default profile and Gear at default tolerance do not resolve this dip.
     Gear alone also moves the failing `-0.78*V_REF` code by 1 LSB (214 ->
     213). Neither change alters a verdict.

**Not established:** whether the default-settings artefact affects any of
the other eight DC corners. Only the baseline corner was audited. Also not
established: whether `reltol=1e-4` is converged for power. The two
tighter-tolerance profiles disagree by 0.9 %.

## Decision

1. **Solver settings are a named policy** applied once, at deck assembly
   (`SOLVER_PROFILES` in `run_conversion.py`). They are no longer `.options`
   strings scattered across execution branches. Every record names the
   profile it ran and states the resolved `.options` card in its
   Environment block.
2. **The reference policy for `sim/full-conversion-transient/` is
   `reltol-gear`: `.options reltol=1e-4 method=gear`.** All other ngspice
   settings stay at their defaults. It applies to every transient this
   runner assembles: the DC corner campaign, `--coherent-sine`, and the
   diagnostic modes (`--mechanism-probe`, `--node-trace`, `--cm-trace`,
   `--decision-margin-trace`). Its scope is this experiment only. No other
   experiment's deck changes.
3. **Every other profile is a labelled SOLVER CONTROL.** That includes
   `ngspice-default`, the settings of every record minted before this DR. A
   control may run the baseline-corner DC transient, `--coherent-sine`, or
   `--solver-audit`. It is refused with `--corners`, with the diagnostic
   modes and with `--supersedes`. Its record never moves `records/LATEST`.
   The runner enforces this before any simulation starts, and `write_record`
   refuses a superseding control.
4. **`--solver-audit` is the standing guard.** It runs the DC baseline
   corner under the reference profile and then each control, one after
   another in one process. It mints one diagnostic record that marks every
   moved observation **SOLVER-SENSITIVE** and separates a moved recorded
   failure mode from a moved value. Any future change to the reference
   policy, the toolchain pin, or the comparator/latch topology re-runs it.
5. **Existing records are untouched.** Records are append-only, and every
   record before this DR is evidence under `ngspice-default`. The next
   reference corner campaign runs under `reltol-gear` and supersedes
   `records/LATEST` through the normal `--supersedes` chain. It is not run by
   this record (see Open items).

## Runtime comparison (date- and commit-stamped)

Simulator wall-clock is measured around the ngspice subprocess only. CI
queue and provisioning time are separate and appear in the second table.

**Like-for-like (one runner, one process, sequential).** DC fragment,
tt/27C/1.8V, 6283 ns simulated. GitHub-hosted `ubuntu-latest` (4 vCPU), CI
run 38118730394, commit `a6dcdd7`, 2026-10-11. Record
`20261011-064547-a6dcdd7`.

| profile | simulator wall-clock | vs default | timepoints (rejected) | Newton iterations |
|---|---|---|---|---|
| `ngspice-default` | 76 s | 1.00x | 14482 (386) | 52457 |
| `reltol-gear` (adopted) | 127 s | 1.66x | 27091 (4509) | 88263 |
| `reltol-only` | 114 s | 1.49x | 21377 (2812) | 80497 |
| `gear-only` | 74 s | 0.97x | 15988 (890) | 50154 |

CI overhead for that job: about 3 s queue (run created 06:38:41Z, job
started 06:38:44Z). Provisioning took about 30 s, with a cached ngspice-47
build and a PDK fetch. The audit step took 393 s, against a recorded 392 s
of simulator wall time.

**Coherent-sine, N=32, `--sine-switch-trace 9`, 33.3 us simulated.** These
are separate CI jobs on separate runners, so the ratios are indicative, not
like-for-like:

| profile | record | commit, date | simulator wall-clock | job queue / provisioning |
|---|---|---|---|---|
| `ngspice-default` | `20261011-022915-877794b` | `877794b`, 2026-10-11 | 372 s | (not recorded) |
| `reltol-gear` | `20261011-023419-877794b` | `877794b`, 2026-10-11 | 657 s | (not recorded) |
| `reltol-only` | `20261011-064924-ad4bfff` | `ad4bfff`, 2026-10-11 | 522 s | 3 s / 42 s (run 38118797662) |
| `gear-only` | `20261011-064408-ad4bfff` | `ad4bfff`, 2026-10-11 | 217 s | 2 s / 24 s (run 38118803663) |

For the documented campaign shape (9 corners, `--jobs 3`), the adopted
policy adds roughly 3 x 51 s, about 2.5 min, of simulator time per campaign
on this runner class. A coherent-sine N=32 capture grows from about 6 min
to about 11 min.

## Alternatives considered

- **Keep ngspice's defaults as the reference, with the audit as a guard.**
  This costs nothing at run time. Rejected because the defaults have
  produced a false +438 LSB conversion that looked like a converter defect.
  The guard can only flag such an event in the runs it audits (one corner,
  or a traced conversion). It cannot stop one in an unaudited corner or
  record. The cost of making that whole class unlikely is 1.66x simulator
  time, about 50 s per DC corner, so keeping the defaults buys almost
  nothing.
- **`gear-only` (`method=gear` at the default `reltol`).** This is free
  (0.97x), and it removes the #621 artefact. Rejected because at the
  default tolerance it does not converge toward the tighter answer. It
  misses the conversion-3 TOP_N dip that both `reltol=1e-4` profiles agree
  on. It moves the `-0.78*V_REF` code by 1 LSB where both tighter profiles
  keep the default's code. It also leaves the 3 % power uncertainty in
  place. It suppresses the symptom without resolving the fast edges any
  better. The cost of not choosing it is about 50 s per corner.
- **`reltol-only` (`reltol=1e-4`, trapezoidal).** This is 1.49x, about 10 %
  cheaper than the adopted profile, and it also removes the artefact.
  Rejected because it keeps trapezoidal integration. Trapezoidal is not
  L-stable, and its point-to-point ringing at stiff, fast-regenerating nodes
  is the textbook source of spurious latch and flip-flop transitions. One
  removed event is evidence that tighter tolerance suffices there, not that
  it suffices at every corner. Gear provides independent protection against
  that failure class. The cost of not choosing it is about 13 s per DC
  corner.
- **Tighter still (`reltol=1e-5`, a `maxstep` cap, or `method=gear
  maxord=...`).** Not run. The cost would grow further, and no observation
  here demands it. The 0.9 % power spread between the two `reltol=1e-4`
  profiles is the open question it would answer (see Open items). Cost of
  not choosing it: the power figure keeps a stated, not eliminated,
  integration uncertainty.
- **A harness-wide default** (a `.options` card in `sim/harness` for every
  experiment). Rejected as out of scope. The evidence covers only the
  full-conversion transient, the one deck with a regenerative latch driving
  static registers. Other experiments' records would silently change
  meaning. Each experiment can adopt a profile through its own decision.

## Spec lines affected

None. No row, target, tolerance or threshold of `spec/target-spec.md`
changes. `CODE_TOLERANCE_LSB`, the outlier bound and the validity gates are
unchanged. This record changes how the full-conversion experiment integrates
its transients, not what any result is graded against.

## Consequences

- New full-conversion records integrate with `reltol=1e-4 method=gear` and
  say so in their Environment block. Old records keep their meaning as
  `ngspice-default` evidence. Running `--solver-profile ngspice-default`
  reproduces a baseline-corner DC or coherent-sine record as a labelled
  control.
- `--sine-solver-control` no longer selects a control, because its settings
  are now the reference. It is kept only because the committed #621 record's
  cold start uses it.
- **Bad:** controls are refused with `--corners` and every diagnostic mode
  (`--mechanism-probe`, `--node-trace`, `--cm-trace`,
  `--decision-margin-trace`), so `records/LATEST` (the 9-corner campaign) and
  the diagnostic records cannot be reproduced by any CLI invocation after
  this decision; they stand as recorded evidence only.
- **Bad:** about 1.66x simulator time per full-conversion transient, and
  more rejected timepoints (4509 vs 386 at the baseline corner).
- **Bad:** until the next reference campaign is minted, `records/LATEST` is
  evidence under the superseded policy. At the baseline corner its codes are
  confirmed unchanged under the new policy, but its power is about 2.8 %
  high relative to the new policy. The other eight corners are unaudited.
- **Bad:** Gear's numerical damping can understate real ringing. The
  `reltol=1e-4` half and the standing `--solver-audit` (which includes the
  trapezoidal `reltol-only` profile) are the check against that bias.
- The DRAFT Power row's informational figures should be read with about a
  3 % integration-setting uncertainty until a converged figure exists.

## Open items

- **A fresh reference DC corner campaign** under `reltol-gear`
  (`--corners --record --supersedes 20261001-105439-c324f80`) and a fresh
  reference coherent-sine capture, both off-host on the pinned toolchain.
  Tracked as #638.
- **Power convergence.** The two `reltol=1e-4` profiles differ by 0.9 % in
  total power. A `reltol=1e-5` point at the baseline corner would bound the
  residual integration error before any Power target is proposed.
- **Corner coverage of the audit.** `--solver-audit` covers the baseline
  corner only. A multi-corner audit is a `klt sim` / batch request, not a
  local grid (host rules).

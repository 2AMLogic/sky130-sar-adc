# DR-006: SAR sequencer bit-count and clock-phase timing budget

- **Status**: proposed — this record ratifies nothing. It documents, as
  provisional, the bit-count and timing-budget inputs `design/sar_sequencer.sch`
  (issue #55) was sized against, each traceable to a DRAFT `spec/target-spec.md`
  row or to `spec/decision-records/DR-003-numeric-spec-derivation.md` (itself
  `proposed`, pending #27's operator ratification).
- **Date**: 2026-08-21
- **Decided by**: Builder agent, issue #55
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #55 (this sub-block), #24 (T1 design-sources decomposition this
  is a split of), #26 / DR-003 (the numeric-spec derivation this record's `N`
  input is confirmed-not-ratified by), #27 (operator ratification DR-003 feeds
  and this record inherits the "not yet binding" status of),
  `spec/target-spec.md` (read, not modified), `design/sar_sequencer.sch` (the
  schematic this record's decisions parameterize),
  `sim/sar-sequencer-behavioral/` (the standalone testbench that exercises it)

## Context

Issue #55 asks for a SAR logic / sequencer and clock/phase-generation
schematic on `sky130_fd_sc_hd`, with its bit-count and timing budget recorded
as provisional (with derivation) rather than assumed. Two `spec/target-spec.md`
rows drive those two numbers, and both are DRAFT, unratified until #27 closes:

- **Resolution `N`** — draft row: `10 bit`. DR-003 Item 2 independently
  confirmed `N = 10` (not challenged) as part of its own V_REF/LSB/CDAC
  derivation, but DR-003 itself is `proposed`, not ratified — so this record
  treats `N = 10` as **provisional, citing DR-003 Item 2**, not as settled.
- **Sample rate** — draft row: `100 kS/s–1 MS/s`. DR-003 Item 5 explicitly
  declined to re-derive this row (no switch-`R_on`/CDAC settling data exists
  yet — that needs #24's full hierarchy). This record does not re-derive it
  either; it is used here only as an *input range* to compute a clock-rate
  budget, exactly as DRAFT as the row itself.

**What this record is not.** It is not a settling-time analysis (no CDAC or
comparator netlist exists yet to settle against) and not a spec change. It
states the two numbers `design/sar_sequencer.sch` was built to, and how they
were derived from the DRAFT rows above, so the schematic's parameterization
is traceable rather than a bare assumption.

## Decision

### Bit count: `N = 10` (provisional, per DR-003 Item 2)

`design/sar_sequencer.sch` implements a fixed **10-bit** successive-approximation
register and an `N+1 = 11`-stage phase sequencer (10 bit-trial phases plus one
end-of-conversion phase). If a future ratification (#27) changes `N`, the
sequencer's stage count and OR-tree fan-in (Consequences, below) must be
regenerated to match — this schematic is not parametric in the netlist itself
(see Open items).

### Phase count and per-phase clock allocation: `N+2 = 12` master-clock periods per conversion, one period per phase, uniform

`design/sar_sequencer.sch`'s ring sequencer produces exactly `N + 2` one-hot
phases per conversion cycle, each lasting exactly one master-clock (`CLK`)
period:

```
1 SAMPLE phase + N bit-trial phases (MSB first) + 1 EOC phase = N + 2 = 12 phases
```

**Adopted here as the simplest defensible provisional allocation: every phase
gets exactly one `CLK` period, uniformly** — no phase (including SAMPLE) is
given extra settling margin over any other. This is a deliberate
simplification, not a settling-time result: a real allocation (e.g. a longer
SAMPLE phase for CDAC top-plate settling, or a longer phase for the
comparator's slowest bit) requires a CDAC/switch/comparator netlist this repo
does not have yet (per DR-003 Item 5, the same open dependency). Adopting
uniform 1-period phases now keeps the sequencer's timing budget traceable to
something concrete (a clock-rate range, below) without guessing at a
non-uniform split this record has no data to justify.

### Derived master-clock frequency range: `1.2 MHz – 12 MHz` (provisional)

Given `N + 2 = 12` `CLK` periods per conversion and the DRAFT sample-rate row
(`f_s`, provisional `100 kS/s–1 MS/s`):

```
f_clk = (N + 2) * f_s = 12 * f_s

f_clk,min = 12 * 100 kS/s = 1.2 MHz
f_clk,max = 12 * 1 MS/s   = 12 MHz
```

This is the `CLK` frequency range `sim/sar-sequencer-behavioral/`'s testbench
exercises (see that experiment's `tb.json`-equivalent manifest / record for
the exact frequency simulated). It is a mechanical consequence of the two
DRAFT rows above, not a new claim about either row.

### Liberty/STA 100 °C ceiling — carried forward from DR-003 Item 5, not re-litigated here

DR-003 Item 5 flagged that `sky130_fd_sc_hd`'s Liberty timing-characterization
libraries top out at 100 °C, while this repo's actual (and only committed)
verification methodology for the digital sequencer is transistor-level
ngspice simulation (no OpenSTA/Liberty step exists or is scheduled). That
conclusion is unchanged by this record: `design/sar_sequencer.sch` is verified
only by direct ngspice transient simulation (`sim/sar-sequencer-behavioral/`),
which reads `sky130_fd_pr__{n,p}fet_01v8[_hvt]` device models directly and is
unaffected by the Liberty ceiling. Any *future* Liberty/STA-based signoff of
this sequencer inherits the 100 °C ceiling automatically — named again here,
not re-derived, per DR-003's own framing.

## Alternatives considered

- **Non-uniform phase durations (longer SAMPLE phase, or a longer phase for
  the slowest expected bit-trial).** Rejected for now — no settling-time data
  exists yet (needs a CDAC/comparator netlist, #24's remaining sub-blocks);
  inventing a split here would be guessing, which `spec/target-spec.md`'s own
  "no guessing" convention and DR-003's precedent both forbid. Uniform
  1-period phases is the simplification this record adopts explicitly, not
  silently.
- **Re-deriving the sample-rate row from switch-`R_on`/CDAC settling.**
  Rejected — out of scope for a digital-only sequencer issue with no
  dependency on the front end, CDAC, or comparator (issue #55's own
  "Dependencies: None"); DR-003 Item 5 already named this as #24/#28's future
  work, not this record's.
- **Parameterizing `N` in the schematic itself (e.g. a generator script kept
  in-repo) instead of a fixed 10-bit netlist.** Considered, not adopted for
  this issue's scope — see Open items. The one-off generator used to author
  `design/sar_sequencer.sch` is not committed; regenerating for a different
  `N` is future work if `N` changes.

## Spec lines affected

**None.** This record changes no line of `spec/target-spec.md`. It records,
for `design/sar_sequencer.sch`'s own benefit, how its two provisional inputs
(`N`, the sample-rate range) trace to that table's still-DRAFT rows.

## Consequences

1. `design/sar_sequencer.sch` is committed as a **fixed 10-bit** design (11
   ring stages, 10 SAR-register bits, a 4-gate OR-tree hand-fit to 11 inputs).
   If `N` changes at ratification (#27) or later, the schematic must be
   regenerated to match — it does not self-adjust.
2. `sim/sar-sequencer-behavioral/`'s testbench targets the derived `1.2 MHz–
   12 MHz` `CLK` range as its provisional operating window, tracing directly
   to this record rather than an assumed clock rate.
3. The uniform-one-period-per-phase allocation is a **simplification that a
   later analog-settling-driven timing budget may have to revise** once a
   CDAC/switch/comparator netlist exists (#24's remaining sub-blocks, #28's
   corner campaign) — this record does not claim the allocation is
   sufficient for real settling, only that it is the traceable baseline this
   sub-block could support without that data.

## Open items

- **Non-uniform, settling-driven phase timing** — deferred to the future
  work DR-003 Item 5 already named (needs #24's CDAC/switch/comparator
  netlist and #28's corner campaign).
- **Parametric regeneration for a different `N`** — if #27 ratifies a
  different resolution than 10 bit, this schematic (and this record's
  frequency-range arithmetic) needs a follow-on update; not automated here.
- **Ratification itself** — the operator's act (#27), per `CLAUDE.md`'s "the
  spec is a gate" rule. Nothing in this record is binding until #27 closes,
  and DR-003 (which this record's `N` input depends on) is also unratified.

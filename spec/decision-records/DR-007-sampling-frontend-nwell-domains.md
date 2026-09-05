# DR-007: the sampling front end's PFET n-well domain partition

- **Status**: proposed — this record ratifies no *spec table* value. It fixes
  a layout-structural rule that follows from an already-documented circuit
  requirement (`DR-004`'s floating-body note), so that every later layout of
  this sub-block is constrained by it rather than re-deriving it.
- **Date**: 2026-08-25
- **Decided by**: Builder agent, issue #122
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #122 (this record's issue), #99 (the full sampling-frontend
  layout this unblocks), #52 (`design/sampling_frontend.sch`),
  `spec/decision-records/DR-004-sampling-frontend-sizing.md` (the circuit
  requirement this record makes structural),
  `layout/sampling-frontend-wells/` (the verified composition and its
  evidence record), `layout/sampling-frontend-wells/reports/LATEST`

## Context

`design/sampling_frontend.sch`'s header and `DR-004`'s "floating-body note"
already document a *non-standard* PFET body tie, verified against a real
leakage bug found while deriving the circuit: `Sa_p`/`Se_p` tie their PFET
body to `BOOST_P`, and `Sa_n`/`Se_n` to `BOOST_N`, because those nodes rise
above VDD during sampling and a fixed-VDD body would forward-bias the
drain/body junction once BOOST exceeds VDD by a diode drop. The remaining five
PFETs (`Scp_p`, `Cmswp_p`, `Invp`, `Cmswp_n`, `Scp_n`) tie body to VDD
normally.

That requirement is stated in `DR-004` as a *circuit* fact. Nothing said what
it costs in layout, and the cost is not obvious: a PMOS body is not a wire —
it is the n-well the device physically sits in. Honouring three distinct body
nets therefore forces three physically separate n-well islands, each with its
own tap, separated by at least sky130's `nwell.2a` minimum spacing. A layout
that does the conventional thing — one n-well over the whole PFET set, tapped
to VDD — passes DRC, extracts nine PFETs, and gets every source/gate/drain net
right, while being electrically wrong in exactly the way `DR-004` forbids.
Issue #99's investigation flagged this as unproven and blocked on it.

**Verified** (issue #122, `layout/sampling-frontend-wells/`, record
`reports/LATEST`): the partition below is drawable, is DRC-clean against
sky130's own n-well rules, extracts with each PFET body on its own island's
tap net, and is LVS-clean against a schematic-derived reference — with a
body-terminal-only negative control proving LVS can see the body column at
all. **Not verified here**: any parasitic, area or matching property of that
particular arrangement (see Open items).

## Decision

The sampling front end's nine PFETs partition into **three n-well domains**,
and any layout of this sub-block must draw them as three physically separate,
individually tapped n-well islands:

| Domain | n-well tap net | PFETs |
| --- | --- | --- |
| boosted, positive side | `BOOST_P` | `Sa_p`, `Se_p` |
| boosted, negative side | `BOOST_N` | `Sa_n`, `Se_n` |
| supply | `VDD` | `Scp_p`, `Cmswp_p`, `Invp`, `Cmswp_n`, `Scp_n` |

Binding consequences of that partition, for any layout of this sub-block:

1. **Islands are separated by at least sky130's `nwell.2a` minimum n-well
   spacing (1.27 µm).** Closer than that they are not separate wells at all —
   the rule's own wording is "merged if less".
2. **Each island's tap is routed to its domain's own signal net**, not to a
   separate well supply, and not left floating. `BOOST_P`/`BOOST_N` are the
   nets the devices' own source/drain terminals already carry.
3. **No `nwell.pin` (64/5) well label may be drawn to name a well.** A drawn
   label names the well even when the tap routing is broken, which converts
   the extraction check from a measurement into a tautology. The name must
   arrive through real connectivity.
4. **The body assignment is verified from extraction, per device, not
   inferred.** `klt extract`'s `unbiased_pmos_body_nets` being empty is
   necessary but *not* sufficient: a single VDD-tied well over everything also
   satisfies it. The per-device body net must be asserted, and an LVS negative
   control that moves only the four boosted bodies to VDD must report
   `mismatch`.
5. **The n-well rules must be checked with a deck that carries them.**
   `klt drc --deck sky130` at klt 0.3.0 carried no n-well rules at all, so it
   reported a well-spacing violation as "clean"; klt 0.4.0 closed that gap
   (2AMLogic/klayout-tools#1420) by adding it directly to the curated deck.
   See `layout/sampling-frontend-wells/README.md` for the measurement and its
   negative control.

This record fixes the *partition and its verification obligations*. It does
not fix a floorplan: island shape, device order and area are a layout choice,
so long as each domain stays contiguous enough for one island per domain.

## Alternatives considered

- **One VDD-tied n-well over all nine PFETs (the conventional layout).** Not
  chosen because it contradicts `DR-004`: `Sa`/`Se` would forward-bias their
  drain/body junction whenever `BOOST_x` exceeds VDD by a diode drop, which is
  most of the sampling phase near full scale. The cost of *not* choosing this
  is real — three islands cost area (`nwell.2a` gaps plus per-island taps) and
  constrain device ordering. The cost of choosing it is a silent electrical
  defect that DRC and a body-blind LVS would both pass, which is worse.
- **Four islands, one per boosted node plus one per side's supply PFETs.** Not
  chosen: `Scp_*`, `Cmswp_*` and `Invp` all tie body to VDD, so splitting them
  further buys no electrical property, costs two more `nwell.2a` gaps, and
  invites a later reader to think the split means something it does not.
- **Deep n-well (`dnwell`) isolation for the boosted devices.** Not chosen:
  sky130's `dnwell` isolates a *p-well* from the substrate (it is aimed at
  isolating NMOS bodies), which is not the problem here — the boosted devices
  are PMOS and already sit in their own n-type body. It would add `dnwell.1`
  (3.0 µm width) and `nwell.7` (4.5 µm dnwell-to-nwell separation) area for no
  benefit to this requirement.
- **Leaving the boosted bodies on the extractor's synthesized proxy net (the
  `device.body_unverified` limitation `layout/trivial-cell/README.md`
  documents).** Not chosen: that is precisely the state in which the layout
  makes no body claim at all, which is what #99 was blocked on.

## Spec lines affected

None. `spec/target-spec.md` has no row about body ties or well structure, and
this record adds none — it is a structural/architecture record of the kind
`spec/README.md` requires for "any architecture choice that constrains
downstream design", not a spec-table change. It leaves `DR-004` in force and
unmodified; `DR-004` states *why* the body tie is what it is, this record
states *what a layout must therefore draw*.

## Consequences

- **#99 is unblocked on this axis.** The full sampling-frontend layout
  inherits a verified recipe (`layout/sampling-frontend-wells/README.md`,
  "The recipe") and a per-device expectation table it can assert against,
  instead of an open question.
- **The floorplan is constrained.** Each domain must stay contiguous enough to
  be covered by one island, and two `nwell.2a` gaps plus three taps are area
  that a single-well layout would not spend. A future area optimisation must
  not merge islands to recover it.
- **Verification of this sub-block's layout is more expensive than the
  comparator's.** It needs a second DRC deck (for the n-well rules klt's
  curated deck omits, plus that deck's own negative control), a per-device
  body assertion, and a body-tie LVS negative control — four verdicts beyond
  what a conventional single-well block needs. That cost is the point: the
  failure being guarded against is invisible to the ordinary verdicts.
- **A `klt` upgrade could change the picture.** If a future klt release adds
  n-well rules to its curated sky130 deck (filed generically as
  `2AMLogic/klayout-tools#1420`), or lets a caller pass deck variables to
  `--engine klayout` (`#1302`, closed upstream but not in a release as of
  2026-08-25), the workaround deck in `layout/sampling-frontend-wells/drc/`
  becomes redundant and should be retired rather than maintained in parallel.
  Likewise, `#1421` asks for the generator primitive that would replace the
  hand-composition in `layout/sampling-frontend-wells/bin/build_layout.py`;
  the *rule* this record fixes survives either change, only its
  implementation would move.
- **This record says nothing about whether the arrangement is *good*.** It is
  correct and verified; it is not optimised.

## Open items

- **Parasitic loading of `BOOST_P`/`BOOST_N` by their own well islands.** An
  island tapped to a boosted node adds well-to-substrate junction capacitance
  *on that boosted node*, which is exactly the high-impedance node
  `sim/sampling-frontend/`'s settling result depends on. Not quantified here
  (this record's evidence is a composition study on a deliberately
  uncompacted floorplan, so its numbers would not transfer). Settled by a
  `klt pex` pass on #99's real layout, the way `layout/comparator/pex/`
  (issue #112) settled the comparator's analogous question.
- **Island-to-island coupling and latch-up margin.** Two n-wells at different
  potentials 1.27 µm apart is rule-legal; whether this block wants more than
  the rule minimum (guard structures between islands, wider gaps) is a
  reliability judgement no evidence in this repo bears on yet. Settled by a
  later DR if #99's layout review raises it.
- **Whether the `VDD` domain should carry a substrate/guard structure of its
  own.** The composition study draws no p-substrate tie because it contains no
  NMOS; #99's real layout does contain NMOS and will need one, and where it
  sits relative to these islands is that issue's call.

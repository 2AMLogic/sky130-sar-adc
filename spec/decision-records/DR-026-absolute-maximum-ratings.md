# DR-026: Absolute limits for this block, sourced to the PDK's own device bounds — three pin classes bounded, four rows left explicitly open

- **Status**: proposed. This record **states limits**; it measures nothing,
  changes no row of `spec/target-spec.md`'s `## Target table`, and does not
  move any existing row's Target or Status cell. Ratification is the
  operator's approval of the PR that carries it, on the same
  ratification-via-PR route DR-003 took through #27.
- **Date**: 2026-11-13
- **Decided by**: Builder agent, issue #834 (scope: state the block's
  absolute limits from PDK-published device bounds, or name the gap)
- **Supersedes**: none
- **Superseded by**: (none while this record stands)
- **Related**: #834 (this decision), #121 (the `rules-4.html`
  reconciliation pass that surfaced the gap),
  [#836](https://github.com/2AMLogic/sky130-sar-adc/issues/836) part (b)
  (padframe overvoltage protection — an operator decision that consumes
  this record's pin bounds as an input, and is **not** settled here),
  [DR-001](DR-001-supply-flavor-scope.md) (the ratified 1.8 V core flavour
  these bounds are read for), [DR-003](DR-003-numeric-spec-derivation.md)
  (the ratified `V_REF`, LSB and PVT corner set),
  [DR-010](DR-010-digital-supply-domain-partition.md) (the `VDD`/`GND` vs
  `VPWR`/`VGND` domain split this record's pin classes follow).
  **PDK pin**: `sim/pdk.json`, open_pdks
  `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`, variant `sky130A`.
  **Where the requirement is graded**: `docs/chipalooza/challenge-4-proposal.md`
  §2.2.2 (content-list reconciliation) and §7 item 12(a).

## Context

`https://opencircuitdesign.com/chipalooza/rules-4.html` (published
2026-11-09, fetched 2026-11-13, sha256
`120db18a0d7781d7c94680888f79e2158e67327bd90b0c6fbe4ee6f6ddc8b4fb`) item 4
requires a proposal to state "absolute limits", and separately requires
conformance to "all requirements of the Sky130 process (i.e., DRC, voltage
limits, etc.)". This repository had never stated any: before this record,
neither `spec/target-spec.md` nor `docs/chipalooza/challenge-4-proposal.md`
contained the string "absolute limits", and no decision record bounded a
pin. The ±10 % supply span DR-003 ratified (1.62 / 1.80 / 1.98 V) is a
**verification grid** — the points the corner runner sweeps — and using it as
a limit would be an interpretation this repo has never made.

**What the pinned PDK install does and does not carry — verified, not
assumed.** Every command below runs against the whole installed `sky130A`
variant (open_pdks `f6eeac7d`), and each comment is that command's actual
output on this host:

```
cd "$PDK_ROOT/$PDK"                                       # ~/.ciel/sky130A here
find . -type f | wc -l                                                            # 8380
grep -rIl -i -E 'absolute max|absolute limit|maximum rating|damage threshold' .    # 0 files
grep -rIl -i -E 'operating voltage' .                                             # 0 files
find . -type f \( -name '*.md' -o -name '*.rst' -o -name '*.txt' -o \
                 -name 'README*' \) | wc -l                                       # 17
```

**Both greps return nothing**, over all 8380 files. The last command is
there to say what the tree *does* hold, because the first draft of this
record claimed it held "no prose documentation at all" and that was wrong:
there are 17 README/`.txt` files, all tool-usage notes for the bundled
xschem, KLayout and magic setups and the ngspice test harness. None states a
device limit — they are inside the 8380 the two greps already swept, and a
further `grep -i -E 'volt|rating|breakdown'` over just those 17 returns two
hits, one about xschem's voltage *sources* and one naming a comparator
testbench. The installed tree is models, decks, abstracts, libraries and
tool notes, and it publishes no device rating anywhere.

So acceptance criterion 1 of #834 — "cited by path/file" — is **not
satisfiable from the installed tree alone**, and this record cites the
SkyWater PDK's own published documentation for the device bounds, with the
installed tree used to corroborate where it can.

**The one source that does publish device bounds**, and the exact words it
uses:

- SkyWater SKY130 PDK documentation, *Device Details*,
  `https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html`
  — fetched 2026-11-13, sha256
  `0a7ec55952b9d164421ece31221ce05727db96c1a4e34de0abb77ad6bea6c959`.
  Its reST source, which is the stabler citation of the same content,
  `https://skywater-pdk.readthedocs.io/en/main/_sources/rules/device-details.rst.txt`
  — fetched 2026-11-13, sha256
  `506021827f52b26673daf8b580f8d79d408724af3138a65695bde86e5c1c6e49`.
  Both hashes re-fetched and confirmed byte-stable within the same session.

**What kind of limit that source actually gives, stated plainly because it
changes what may be claimed.** Every per-device bound on that page sits under
the heading **"Operating Voltages where SPICE models are valid"**. That is a
*model-validity range*: the span over which SkyWater warrants its extracted
BSIM/subcircuit models, not a foundry-stated damage threshold or
absolute-maximum rating in the datasheet sense. The page publishes no
breakdown voltage, no stress rating and no reliability (TDDB/HCI) lifetime
for any device. **This record therefore states the best available
PDK-sourced bound for each pin class, and says so — it does not state, and
must not be read as stating, a damage threshold.**

**Which device entries are relevant is counted from the netlist, not
assumed.** The regenerated top-level netlist `design/sar_adc_top.spice`
instantiates exactly three PDK primitives — `sky130_fd_pr__pfet_01v8` (37
instance lines), `sky130_fd_pr__nfet_01v8` (36) and
`sky130_fd_pr__cap_mim_m3_1` (28) — with no other `sky130_fd_pr__` mention
of any kind in the file, plus `sky130_fd_sc_hd` standard cells, which are
themselves built from the same two 1.8 V core FETs. A fourth primitive,
`sky130_fd_pr__res_generic_po`, exists in this repository but **not in the
ADC**: its two instances are in `design/smoke_test.sch`, a harness smoke
test. It is carried in this record's open items for completeness, not
because the converter depends on it.

Verbatim from the cited source:

| Device | Published bound |
|---|---|
| `sky130_fd_pr__nfet_01v8` | `V_DS` = 0 to 1.95 V; `V_GS` = 0 to 1.95 V; `V_BS` = +0.3 to −1.95 V |
| `sky130_fd_pr__pfet_01v8` | `V_DS` = 0 to −1.95 V; `V_GS` = 0 to −1.95 V; `V_BS` = −0.1 to +1.95 V |
| MiM capacitors (cells `sky130_fd_pr__cap_mim_m3__base` / `..._m4__base`) | `\|V_c0 − V_c1\|` = 0 to 5.0 V |
| Generic resistors (incl. `sky130_fd_pr__res_generic_po`) | **no operating-voltage line is published** |

**Corroboration from inside the pinned install**, for the 1.95 V figure
only: the `sky130_fd_sc_hd` Liberty set shipped at this pin is characterized
over `1v28 … 1v95` and `n40C / 025C / 100C`
(`ls "$PDK_ROOT/$PDK/libs.ref/sky130_fd_sc_hd/lib/"`). Its top voltage
corner is **1.95 V**, the same number, reached independently. This is a
*characterization* envelope, a third kind of bound again — not validity, not
damage — and it is cited here only because it agrees.

**The `cap_mim_m3_1` mapping is a mapping, not a string match.** The
documentation entry names the cells `sky130_fd_pr__cap_mim_m3__base` /
`sky130_fd_pr__cap_mim_m4__base` and describes the two constructions "CAPM
over Metal-3" and "CAP2M over Metal-4". The subcircuit this design
instantiates, `sky130_fd_pr__cap_mim_m3_1`
(`$PDK_ROOT/$PDK/libs.ref/sky130_fd_pr/spice/sky130_fd_pr__cap_mim_m3_1.model.spice`),
is the sized CAPM-over-Metal-3 variant — its own parameters (`camimc`,
`cpmimc`, `rm3`, `rcvia3`) identify it as that construction. The 5.0 V bound
is read across that mapping, which is stated here rather than left implicit.

## Decision

**This block's absolute limits are stated as the table below, for the pin
classes the PDK's published device bounds reach, and as named open gaps for
the rest.** All voltages are with respect to the pin's own domain return
(`GND` for the analog domain, `VGND` for the digital domain, per DR-010).

| Pin / quantity | Limit | Kind of limit | Sourced from |
|---|---|---|---|
| `VDD` (analog supply) | 0 to **1.95 V** | PDK model-validity bound | `nfet_01v8`/`pfet_01v8` `V_DS`/`V_GS` |
| `VPWR` (digital supply) | 0 to **1.95 V** | PDK model-validity bound | same two FETs (the `sky130_fd_sc_hd` cells are built from them); corroborated by the `1v95` Liberty top corner |
| `VINP`, `VINN`, `VCM` (analog inputs) | 0 to **1.95 V**, and never above `VDD` | derived (below) from the PDK model-validity bound | `nfet_01v8`/`pfet_01v8` terminal-pair bounds |
| `VREFP`, `VREFN` (reference inputs) | 0 to **1.95 V**, and never above `VDD` | derived (below) from the PDK model-validity bound | `nfet_01v8`/`pfet_01v8` terminal-pair bounds; MiM plate bound (5.0 V) is looser and does not bind |
| `CLK`, `RST_B` (digital inputs) | 0 to **1.95 V**, and never above `VPWR` | derived (below) | same |
| `DOUT9..DOUT0`, `BUSY` (digital outputs) | 0 to **1.95 V** | derived (below) | same |
| CDAC unit-cap plate-to-plate | `\|V\|` ≤ **5.0 V** | PDK model-validity bound | MiM capacitor entry; `≈ 2.6×` looser than the 1.95 V pin bound, so it never binds in this design |
| Pin undershoot below the domain return | **OPEN — no PDK-published rating** | — | see Open items 1 |
| Operating temperature | **OPEN — no PDK-published rating** | — | see Open items 2 |
| Storage temperature | **OPEN — no PDK-published rating** | — | see Open items 2 |
| ESD (HBM / CDM) and latch-up current | **OPEN — no PDK-published rating** | — | see Open items 3 |
| `res_generic_po` terminal voltage (smoke test only, not in the ADC) | **OPEN — the PDK publishes no bound for it** | — | see Open items 4 |

**The pin rows marked "derived" are derived, and the derivation is stated so
a reviewer can reject it rather than inherit it.** The PDK publishes
*terminal-pair* bounds (`V_DS`, `V_GS`, `V_BS`), not pin-to-ground bounds. A
pin bound follows from them only through this block's own topology: every
pin in the table above connects, through this design, to gates, sources or
drains of `nfet_01v8`/`pfet_01v8` whose other terminals sit between the
domain return and the domain rail. If the rail is itself held at or below
1.95 V, then holding a pin in `[0, rail]` keeps every one of those terminal
pairs inside the published envelope. That is why each derived row carries
"and never above `VDD`/`VPWR`" — the pin bound is *conditional on the rail
bound*, and is not independently valid if the rail is violated.

**1.95 V is a ceiling on the pin, not a target.** Nothing in this design is
operated at it; the ratified operating point is `V_DD = V_REF = 1.8 V`
(DR-003).

## Alternatives considered

- **Use the ratified ±10 % grid's top point, 1.98 V, as the absolute
  maximum.** Rejected, and the rejection is the substantive content of this
  record. 1.98 V is where the corner runner *sweeps*, which is the opposite
  of a limit: a verification grid asserts the design works everywhere
  inside it, a limit asserts the part is not to be taken outside it.
  Promoting one to the other would also have inverted the sign of the
  finding in Open item 5 below — the grid point is *above* the only bound
  the PDK publishes, so reading the grid as the limit would have concealed
  exactly the conflict this record exists to surface. Cost of not choosing
  it: the proposal states two different numbers (1.98 V grid, 1.95 V limit)
  and has to explain why, which is this record.

- **State nothing until the foundry publishes true absolute-maximum
  ratings.** Rejected. `rules-4.html` item 4 asks for absolute limits and
  the PDK will not supply datasheet-grade ones; leaving the row empty would
  fail the brief's content list while hiding that a PDK-sourced bound does
  exist and is *tighter* than the grid this repo already runs. Cost of not
  choosing it: this record must carry the model-validity caveat in every
  statement of the numbers, which it does.

- **Derive breakdown voltages from the device physics or from the model
  parameters in `$PDK_ROOT/$PDK/libs.ref/sky130_fd_pr/spice/`.** Rejected.
  The BSIM parameter set is fitted for the valid range; extrapolating a
  damage threshold out of it would be an invented number of exactly the kind
  `CLAUDE.md` forbids ("the numbers must come from the PDK's own device
  limits, not be invented"). Cost of not choosing it: the undershoot,
  temperature and ESD rows stay open rather than being filled with
  plausible-looking values.

- **Fold the ratings into `spec/target-spec.md`'s `## Target table` as new
  rows.** Rejected. Every row of that table is a *measured or measurable
  claim* and is gated as one — `sim/check_spec_coverage.py` requires each
  row to carry a bench entry in `sim/spec-coverage.json` unless it is DRAFT.
  An absolute limit is a bound on use, not a measurement, and has no bench.
  The ratings therefore land in their own section of `spec/target-spec.md`,
  outside that table. Cost of not choosing it: the ratings are not swept by
  the spec-coverage gate, so nothing machine-checks that they stay in sync
  with this record — stated here as a known weakness.

## Spec lines affected

- **No existing row of `spec/target-spec.md`'s `## Target table` changes** —
  not its Target cell, not its Status cell. In particular the **Corners**
  row (`−40/27/125 °C, ±10 % supply, sky130 process corners`, RATIFIED,
  DR-003 via #27) is left exactly as ratified. Open item 5 below records a
  conflict with it; it does not resolve it, and this record does not relax
  it.
- **New section** in `spec/target-spec.md`: "Absolute limits — PROPOSED
  (DR-026)", carrying the table above and a sentence distinguishing it from
  the PVT verification grid.
- **New subsection** in `docs/chipalooza/challenge-4-proposal.md` §4,
  "Absolute limits", reporting the same bounds and the same four open gaps,
  for `rules-4.html` item 4.
- `docs/chipalooza/challenge-4-proposal.md` §7 gains item 12, recording what
  landed and what stayed open.

## Consequences

1. **The proposal can answer `rules-4.html` item 4** with sourced numbers
   rather than silence, and the four rows it cannot source are visible as
   gaps rather than absent.
2. **A conflict with the ratified verification grid becomes visible and
   must be dispositioned by someone** — see Open item 5. That is a cost, not
   a benefit: before this record the repo could sweep 1.98 V without anyone
   having to say whether that is inside the PDK's envelope. It now has to.
3. **The pin bounds are an input to #836 part (b)** (padframe overvoltage
   protection). They make that decision statable — a 1.8 V-core block whose
   pins are bounded at 1.95 V, facing a 3.3 V-class periphery, has a
   quantified mismatch rather than a qualitative one. They do **not** settle
   it; no protection network is designed, assessed or proposed here.
4. **No testbench, corner set or `sim/` record changes.** Nothing in `sim/`
   is re-run, invalidated, or re-graded by this record. No existing evidence
   record's verdict moves.
5. **The ratings are not machine-checked.** By the Alternatives decision
   above they sit outside `## Target table`, so `sim/check_spec_coverage.py`
   does not see them and nothing enforces that this record and
   `spec/target-spec.md` keep saying the same thing. A future record that
   changes a bound must edit both by hand.
6. **A model-validity bound is weaker than what the brief's phrase
   "absolute limits" conventionally means.** A reader who expects a foundry
   absolute-maximum table will find a narrower claim. That is the honest
   state of the open PDK and is labelled as such everywhere the numbers
   appear, but it is a real shortfall against the phrase, not a satisfied
   requirement.

## Open items

1. **Pin undershoot below the domain return.** The PDK publishes no negative
   pin rating. The only forward-bias number on the cited page is a
   *bulk-source* bound (`nfet_01v8` `V_BS` = **+0.3** V; `pfet_01v8` `V_BS` =
   **−0.1** V), which bounds a device terminal pair, not a pin excursion
   below `GND`/`VGND`. No undershoot limit is stated here. Settled by: a
   later record, if SkyWater publishes one, or by a characterization
   campaign this repo does not have.

2. **Operating and storage temperature.** The PDK publishes neither. The two
   envelopes that exist in the pinned install are a *characterization* range
   (`sky130_fd_sc_hd` Liberty, −40 … 100 °C) and a model extraction
   reference (`tnom = 30.0` in
   `$PDK_ROOT/$PDK/libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_01v8.pm3.spice`
   and its pfet counterpart) — neither is a rating, and neither is promoted
   to one here. Note that this repo's ratified 125 °C corner is already
   above the Liberty characterization ceiling of 100 °C; DR-003's Option A
   scope note records why that is harmless today (this repo runs no
   Liberty/STA signoff step). Settled by: the operator, or a later record if
   SkyWater publishes a process temperature rating.

3. **ESD (HBM/CDM) and latch-up current.** The PDK's own "Latch-up/ESD
   Criteria" table (Table 3e of *Criteria & Assumptions*,
   `https://skywater-pdk.readthedocs.io/en/main/rules/assumptions.html`,
   fetched 2026-11-13, sha256
   `d736b30ca19ccf55d867af5b36ebcebfaeb254ebb317a4626be063917d6eca5d`;
   reST source
   `https://skywater-pdk.readthedocs.io/en/main/_sources/rules/assumptions.rst.txt`,
   sha256
   `99981cebb004a90f7947abc9461f03cdacc4b1906c94f340359c7aeb13f62edc`)
   is **geometric only** — minimum n+/p+-to-nwell
   spacing `0.23 µm` (`NPNWLU`), minimum nwell enclosure of tap `0.04 µm`
   (`XNWESD`) — and publishes no stress voltage, energy or current. This
   block also has no pads of its own (§2.2 of the proposal: its signals are
   mapped to harness slots), so an ESD rating would in any case be a
   property of the padframe, not of this block. Settled by: #836, or the
   padframe owner.

4. **`sky130_fd_pr__res_generic_po` terminal voltage.** The documentation's
   "Generic resistors" entry publishes no operating-voltage line, and notes
   the generic resistors "are not recommended for analog applications". This
   bounds nothing in the converter — the device appears only in
   `design/smoke_test.sch` (two instances), never in
   `design/sar_adc_top.spice`. Listed so the inventory of PDK primitives
   this repository touches is complete, not because a signal-path pin
   depends on it. Settled by: a later record, if a converter revision ever
   instantiates it.

5. **The ratified grid's top supply point is above the only published
   bound.** DR-003 ratified ±10 % of 1.8 V, so the corner runner's top point
   is **1.98 V** (`sim/harness/corners.py`, `supply_points()`), and committed
   evidence exists at it (e.g. corner id `tt_27c_1.98v` in
   `sim/cdac-array-transfer/records/20260821-062504-433a294.md`). The PDK's
   published model-validity ceiling for both core FETs is **1.95 V** —
   1.5 % lower, i.e. the devices' documented envelope is `+8.33 %` of
   nominal, narrower than the `±10 %` this repo sweeps. **This record states
   the conflict and resolves nothing.** It does not relax the Corners row,
   does not re-grade any evidence recorded at 1.98 V, and does not assert
   that results at 1.98 V are wrong — only that they are reported outside
   the span SkyWater warrants its models over, which no document in this
   repo had said. Settled by: the operator, choosing between (a) ratifying
   the grid as-is with the extrapolation declared, (b) a superseding record
   narrowing the supply axis to the model-validity span, or (c) a record
   that separates the *electrical* limit from the *modelling* limit on
   evidence this repo does not yet have. Until then, every result at the
   1.98 V point carries this caveat.

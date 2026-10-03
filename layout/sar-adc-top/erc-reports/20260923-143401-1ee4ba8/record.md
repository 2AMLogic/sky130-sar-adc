# `klt erc` supply record `20260923-143401-1ee4ba8` — T1 item 11 (Power delivery, structural)

**Verdict: item 11 is UNMET.** Two of this block's four drawn supplies
(`VPWR`, `VGND`) each resolve to **two** disconnected electrical islands, and
`erc.missing_tie` is **not computed**. The two analog supplies (`VDD`, `GND`)
each resolve to exactly one island with no short — so this is a partial, not a
blanket, failure, and the report says which half is which.

Produced by `layout/sar-adc-top/bin/run-erc.sh` (issue #344). This is a
verdict *about* an existing layout record; it regenerates no geometry.

| | |
|---|---|
| Graded layout | `layout/sar-adc-top/reports/20260919-050355-fb11617/sar_adc_top.gds` |
| Layout content hash | `sha256:62038198a3fd58b359d24ec922fa74bc945539e1a019b57d258e46474aacd222` |
| Spec | `layout/sar-adc-top/erc-supply-spec.json` |
| Spec content hash | `sha256:fd4f5a93160072689b6fbc52dcce01b7eab8b68c48e6dc2fb6632500aa929946` |
| Tool | `klt` 0.6.0 / KLayout 0.30.12 (`layout/erc-requirements.txt`) |
| Invocation | `klt erc <gds> <spec> --pdk sky130 --deck sky130 --format json` |
| `status` / `erc_status` | `violations` / `violations` (exit 3) |
| `erc_finding_count` | 2 |

Both content hashes are asserted by `run-erc.sh` itself at the end of every
run, against the files on disk — a drifted hash aborts the run rather than
producing a report that merely looks pinned. The layout hash matches the same
record's own `drc.json`/`extract.json` `provenance.input.content_hash`, so all
three verdicts demonstrably grade the same bytes.

## Per-supply verdict

`status` is **not** the item-11 verdict (an antenna or floating-gate finding
in the same report is a real defect but is not this item's subject —
klayout-tools#1994). The item's own pass conditions are per-supply:

| Supply | Islands | `erc.unconnected_net` | `erc.supply_short` | Item-11 verdict |
|---|---:|---|---|---|
| `VDD` | 1 | none | none | **pass** |
| `GND` | 1 | none | none | **pass**, read narrowly — see below |
| `VPWR` | 2 | **yes** | none | **fail** |
| `VGND` | 2 | **yes** | none | **fail** |
| `erc.missing_tie` | — | — | — | **not computed** — see below |

No `erc.supply_short` of any kind is reported: the four declared supplies are
four mutually distinct islands, so nothing is accidentally rail-to-rail
shorted. No `erc.floating_gate` is reported either.

### The `VPWR`/`VGND` finding is real, and it is already a known gap

```
erc.unconnected_net  VGND  declared net 'VGND' resolves to 2 disconnected electrical islands (expected exactly one)
erc.unconnected_net  VPWR  declared net 'VPWR' resolves to 2 disconnected electrical islands (expected exactly one)
```

The two islands are the two standard-cell macros' own self-contained rails:
`sar_sequencer`'s and `seln_inverters`'. The same record's `lvs.json` names
them independently — its `net_correspondence` carries
`VPB|VPWR` ↔ `VPWR_SEQ` and `VPB|VPWR$1` ↔ `VPWR_SELN` — so the island count
here is corroborated by a second, independently-produced report rather than
resting on this one.

This is **not a surprise and not a spec defect**: it is the integration gap
`design/sar_adc_top.sch` and `layout/sar-adc-top/README.md` ("GND / VPWR /
VGND: not a routing job (mostly)") already document, where neither digital
rail is a formal port of its macro's subckt call at the top level and neither
is tied to anything. What is new is that item 11 now *grades* it: as laid out,
this assembly's digital section has no structural path from any top-level
supply to its own cells, which is exactly the question ("is the supply
connected to what it powers") item 11 exists to ask. Per issue #344's
instruction, the spec was **not** tuned to make this pass — the rails stay
declared and the finding stays in the record. Tracked as its own issue; see
"Follow-ups" below.

### Why `GND`'s pass must be read narrowly

`klt erc` is a purely geometric wire/via connectivity model with no device
recognition. This block's analog ground return is partly the **p-substrate**,
which `klt extract`'s sky130 deck synthesises as one shared `vsubs` net
regardless of drawn geometry and which no geometric model can see. So
`GND: 1 island` means *the drawn GND conductor is one island*, not *every
NMOS body reaches it*. The substrate half is precisely what `erc.missing_tie`
would have graded — and that check was not run.

### `erc.missing_tie`: not computed (absence of evidence, not evidence of absence)

No `ties[]` is declared, so `erc.missing_tie` is **not computed** — it is not
reported as a misleading zero. The report says so in machine-readable form
rather than only in prose:

```json
"ties_disclosure": { "kind": "tool_limitation", "reason": "..." }
"erc_coverage": { "inapplicable": [ { "id": "erc.missing_tie:[]",
                                      "reason": "ties_disclosed_tool_limitation" } ] }
```

`"kind": "tool_limitation"` (not `"unexpressible"`) is the accurate one here:
sky130 taps *are* nameable on this layout (`tap.drawing` 65/44 inside
`nwell.drawing` 64/20, wired to `li1` through `licon1` 66/44). The obstacle is
**klayout-tools#2169** — a `ties[]` declaration on a real routed standard-cell
design collapses into one electrical island and reports a **false**
`erc.supply_short`. Declaring `ties[]` would replace a stated gap with a
misleading finding, so it is left undeclared and disclosed.

**Well-tie evidence standing in for the ungraded check** (named so a reader
can go look, not asserted):

1. **Tap cells are instantiated.** `klt place-and-route`'s own tap cells are
   present in the graded GDS by name — `sky130_fd_sc_hd__tapvpwrvgnd_1` text
   on `text.drawing` 83/44 — and 11 `tap.drawing` 65/44 shapes are drawn.
2. **Body/tub nets are labelled.** `VPB` on `nwell.label` 64/5 and `VNB` on
   `pwell.label` 64/59.
3. **LVS net correspondence** (`reports/20260919-050355-fb11617/lvs.json`)
   carries the supply nets: `VDD` ↔ `VDD` (pin), plus the two digital rails
   above.

Item 11 is kind-dependent, and this is an **analog** block (whole-custom,
transistor-level; no RTL flow in-repo — `docs/t1-gap.md`), so the analog
column applies: item 4's own LVS report must carry the supply nets in its
`net_correspondence`. It does — **but only partially, and item 4 does not
itself pass**: that LVS run's `status` is `mismatch`, and neither `GND` nor
`VGND` appears in its `net_correspondence` at all. Stand-in (3) is therefore
weaker than a clean LVS would make it, and is recorded that way on purpose.

## Cross-checks

Each of these was run; none is assumed.

**1. The verdict does not depend on the `klt` version bump.** The same spec
and GDS on the repo-pinned `klayout-tools==0.5.0` (`layout/requirements.txt`,
`layout/.venv`) reports the *same two findings* with the same net names and
island counts. What 0.5.0 cannot do is pin that verdict to its input: its
`klt erc` emits no `provenance` block at all (see
`layout/erc-requirements.txt`).

**2. The verdict does not depend on `--deck sky130`.** Dropping the flag
leaves the supply findings byte-identical (same two `erc.unconnected_net`
entries). The flag matters for the *antenna* half and for signal nets, not for
the supplies — see 4.

**3. The stackup is necessary, not padded.** Ablating it makes supplies split,
which is the evidence that every declared level is load-bearing:

| Spec | `VDD` | `VPWR` | `VGND` |
|---|---:|---:|---:|
| as committed | 1 | 2 | 2 |
| minus `via3` (70/44) | **3** | 24 | 24 |
| minus `met4`/`met5` + `via3`/`via4` | **2** | 22 | 22 |

`VDD` is genuinely routed through met4 — the top-level assembly crosses the
CDAC on met3/met4 — so a stackup stopping at met3 would have reported a
*false* split of the one supply that actually passes.

**4. MiM capacitors, and why `--deck sky130` is used.** A sky130 MiM cap's
top-plate via necessarily overlaps its own bottom-plate met3 (the DRM requires
it), so a plain `via3 = met3↔met4` bridge shorts every cap plate-to-plate.
Measured on this layout: **1028 of 1477** merged `via3` (70/44) shapes land on
a `capm` (89/44) plate; only 449 are ordinary routing vias. Without
`--deck sky130` that produces one merged island spanning
`BPREF_N, BPREF_P, TOP_N, TOP_P, VINN, VINP, VREFN` and one antenna violation
(`met1` ratio 477.3 > 400, `met2` 1208.9 > 400) on it. `--deck sky130`
(klayout-tools#2183/#2204) carves the declared deck's `cap_mim` bodies out —
`provenance.devices` echoes the carve-out, 41.15 µm² on `via3` — and the
merged island and that antenna violation both disappear. **No declared supply
is in that merged island either way**, which is why cross-check 2 comes out
clean.

## Antenna half (reported, not this item's subject)

210 gate nets, gate area computed as `poly ∩ diff` via
`stackup[0].active_layer` (klayout-tools#1979). Every gate reports
`antenna_verdict: "pass_partial"` and **zero** levels violate. `pass_partial`
rather than `pass` is expected, not a defect: sky130's published antenna table
covers li1/met1/met2 only, so the met3/met4/met5 levels this block declares
are `"unchecked"` — a coverage gap in the PDK's own rule table, recorded
rather than papered over.

## Friction filed upstream (the canary's other job)

Two generic `klt erc` gaps were hit producing this record and filed at
`2AMLogic/klayout-tools`, described as tool gaps with no design detail:

- **klayout-tools#2400** — `nets[]` matches supplies by label *string*, so a
  stream where one string legitimately names more than one intended net
  (independent domains reusing a macro library's PG pin names) cannot be
  declared at all: `erc.unconnected_net` fires identically for "one net
  accidentally fragmented" and "N nets intended to be independent". Directly
  relevant to how #355 resolves — if the decision there is "keep the digital
  domain independent with its own top-level pins", item 11 stays
  unsatisfiable for this block until #2400 lands.
- **klayout-tools#2401** — a mis-transcribed `stackup[].label_layer` is
  silent: every declared net matches zero islands and reports as
  `erc.unconnected_net`, indistinguishable from a real supply defect. This
  spec dodged it only because the sky130 `.pin` (datatype 16) vs `.label`
  (datatype 5) split was checked against a text dump of the graded GDS before
  the spec was written — see `erc-supply-spec.json`'s layer-provenance note.

Not filed, because it is already open upstream: **klayout-tools#2243** (the
spec validators silently drop unrecognised keys). This spec's inline
justification blocks are `_comment` keys, which works *because* of that
leniency — item 11's own acceptance criteria require an inline-commented
spec, and JSON has no comment syntax, so the artifact rests on behaviour
#2243 points out is undocumented.

## Follow-ups

- **`VPWR`/`VGND` two-island finding** — filed as its own repo issue rather
  than fixed here, per issue #344: tuning the spec until it passes is
  forbidden, and connecting the digital rails is a top-level routing change to
  `layout/sar-adc-top/bin/build_layout.py` that must re-run the whole
  place/route/DRC/LVS flow and mint a new `reports/<id>/` record.
- **Staleness rule.** This record grades one specific GDS by content hash. A
  new `reports/<id>/` record from `run-flow.sh` makes this one stale, not
  wrong — re-run `run-erc.sh` to mint a fresh ERC record beside it.

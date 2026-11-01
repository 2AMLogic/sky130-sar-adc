# Digital-partition multi-corner STA (T1 item 5, digital)

`klt sta` (OpenSTA via OpenROAD) on the **routed** DEFs of the two digital macros,
over a declared Liberty corner set, at the DR-006 12 MHz clock:

| Macro | Routed DEF |
|---|---|
| `sar_sequencer` | `layout/sar-sequencer/reports/20261012-113813-743bcd0/sar_sequencer.def` |
| `top_glue` | `layout/top-glue/reports/20261012-113946-743bcd0/top_glue.def` |

`requests/<macro>.12mhz.json` is the claim; `requests/<macro>.negative-control-6ghz.json`
is the same request at an over-fast clock (T = 0.16667 ns, the SPICE campaign's own
too-fast value) and must fail setup at every corner. `bin/run-record.py` runs all
four, **refuses to write a record unless the positive runs are clean and the
negative controls fail**, and mints `runs/<id>/` + `records/<id>.md`.

## Corner set: one committed place

`corner-set.json` lists the nine PVT points `sim/digital-partition/` characterizes,
which of them have a stock `sky130_fd_sc_hd` Liberty file, and the supplementary
corners that were timed in addition. `#679` cites this file.

**Of the nine points, eight have no Liberty file and are declared gaps; none is
substituted.** `tt_27c_1.80v` is timed with `tt_025C_1v80`, a declared mapping
(25 C file for a 27 C point), not an identity. The corners actually timed are
`tt_025C_1v80`, `tt_100C_1v80`, `ss_100C_1v60`, `ff_n40C_1v95`; the last three are
stock extremes that are *not* among the nine and do not stand in for any gap.

## Constraints are assumptions, not spec values

Ideal clock (`klt sta` 0.6.0 cannot propagate the routed clock tree, so
register-to-register hold slack omits skew), input and output delays of 0.25 T
(the SPICE campaign's `COMP_OUT` arrival is also 0.25 T), no driving cell, no
output load, no SPEF. The result is the digital partition's timing at its own
boundary under those assumptions. **It says nothing about the ADC conversion
rate**, which also depends on the analog partition. `top_glue` is purely
combinational; its worst setup slack (about 20.8 ns) is close to what the I/O
budget alone leaves (T/2 - 0.25 T), and the limiting path was not extracted.

## Other limits

- The routed `sar_sequencer` is the 36-instance issue-#102 netlist, not the
  57-instance schematic (issue #680) (see `../digital-functional/README.md`).
- Provisional: `spec/target-spec.md` is DRAFT (issue #1); the 12 MHz figure is
  the DR-006 planning value.
- The reports name a scratch copy of the DEF (`/tmp/klt-sta-*/…`), byte-identical
  to the committed one (hash asserted by the runner); `runs/<id>/executed-requests/`
  holds the requests as run. This keeps `klt signoff --check` identical on every
  checkout. `signoff/check_evidence_hashes.py` re-hashes the real DEF.

## Reproducing

```bash
python3 -m venv .venv-signoff && .venv-signoff/bin/pip install -r signoff/requirements.txt
export PDK=sky130A PDK_ROOT=<dir that holds sky130A>
KLT=.venv-signoff/bin/klt python3 -I sim/digital-sta/bin/run-record.py
```

## Post-route SDF (issue #679)

`bin/run-sdf.py` mints `runs/<id>/sdf/<macro>.<corner>.sdf` (+ `<macro>.sdf-sta.json`,
`inputs.sha256`, `records/<id>-sdf.md`): `klt extract --parasitics --def-net-connections`
on the routed GDS, then `klt sta` with `spef` + `sdf: true` at the four corners.
`--def-net-connections` matters: without it only 44 of 240 SPEF nets resolved against
the DEF-linked design and the delays did not change. The SDFs are consumed by
`../digital-functional/bin/run-sdf-record.py`. Needs `PDK_ROOT` at the open_pdks
revision the layout was minted under (`f6eeac7`); see the record for limits.

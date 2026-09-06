## DRC Report: sampling_frontend.gds
**Status:** ✅ clean
- Deck: sky130
- File: sampling_frontend.gds

No violations found.

## LVS Report: sampling_frontend.gds vs reference.spice
**Status:** ✅ match
- Top: gen_compose_0
- Engine: klayout

| Category | Severity | Side | Description |
| --- | --- | --- | --- |
| device.body_unverified | warning | layout | 11 NMOS device body terminal(s) were compared against the 'vsubs' deck-synthesized substrate net, not a real schematic net -- no drawn substrate-tap geometry resolved these device(s)' body terminal to a real net (see docs/cli/extract.md, "Coverage") |
| topology | warning | layout | device class has no counterpart on the other side, but no devices of this class were extracted either -- not a real topology mismatch |

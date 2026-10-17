# Probe: `erc.missing_tie` on two n-wells (issue #684)

Graded GDS: `layout/sar-adc-top/reports/20261001-211249-1ca34e6/sar_adc_top.gds`
(`sha256:9d7c1a4c…916d14b`, in `graded-gds.sha256`; the same hash as the ERC
record cited in #684). Tool: stock `klayout -b` 0.28.16 (`klayout-version.txt`).
`klt` was not used, so this is an independent geometry reading, not a re-run of
`klt erc`. Commands: `GDS=<gds> klayout -b -r shape-dump.py` and
`GDS=<gds> klayout -b -r tap-net-trace.py`; raw output in the `.txt` files.

## Shape dump (layers clipped to each well bbox, hierarchy read)

The two wells have identical counts:

| layer | count in bbox |
|---|---:|
| 64/20 nwell (incl. the well island itself) | 3 |
| 65/44 tap | 1 (0.6 x 1.2 um) |
| 66/44 licon1 | 8 (2 inside the tap) |
| 67/20 li1 | 7 (1 pad exactly covering the tap) |
| 67/44 mcon | 7 (1 on the tap pad) |
| 68/20 met1 | 12 (1 stripe from the tap pad to the bbox top edge) |
| 93/44 | 0 |

Tap shapes sit in cell `route__ROUTE` at (64.225,86.450)-(64.825,87.650) and
(90.505,86.450)-(91.105,87.650) um.

## Classification

Both wells: **tap present and wired, but to neither declared rail.** No link
is broken in the layer / licon1 / li1 sense. A flat connectivity trace
(li1, mcon, met1..met5, via..via4; probe point on the tap's li1 pad) puts the
west well's tap on a net carrying text `BOOST_P` and the east well's on
`BOOST_N`, both text on 69/5 (`tap-net-trace.txt`). That matches DR-007, which
ties the boosted-side PFET n-wells to `BOOST_P` / `BOOST_N` rather than VDD. So
the two both-entry flags read as the tie model finding no VDD/VPWR tap on wells
that are deliberately tied elsewhere; they do not read as a missing tap or an
invisible one.

Limits of this reading: the trace is a plain layer-connectivity model written
for this probe, not `klt erc`'s; it was not checked that each well holds
exactly the PFETs DR-007 assigns it; the host klayout (0.28.16) differs from
the repo pin (0.30.12), which should not matter for shape/connectivity reads
but was not tested.

## Not resolved here

- Declaring these wells needs a per-well net selector. On klt 0.6.0 each
  `ties[]` entry applies to every n-well, so a third entry would only add
  cross-flags. The selector (`well_requires` / `well_excludes`) exists in
  klt >= 0.7.0 per ERC record `20261017-193237-9522693e` on PR #682, and is
  owned by #685. `ties[]` itself is only on PR #682's branch, not on `main`.
- No ERC re-mint and no declaration or spec change are made here. Acceptance
  criteria 3 and 4 of #684 remain open until #682 lands and #685 supplies a
  selector.

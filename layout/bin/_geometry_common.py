"""Shared low-level geometry primitive for the layout sub-block
`build_layout.py` scripts.

Used by `layout/comparator/bin/build_layout.py`,
`layout/sampling-frontend-wells/bin/build_layout.py`, and
`layout/sampling-frontend/bin/build_layout.py`, which import this module via
a `sys.path` insert (see either script's own header) rather than a package
install, matching this directory's existing `_record_common.py` /
`_flow_common.sh` shared-module convention.

Houses the byte-identical shell all sub-blocks hand-rolled: the nanometre
database unit, the micrometres -> nanometres converter, and the `Rect` base
class's shared members (`__slots__`, `__init__`, `um()`, `centred()`,
`as_um()`, `hwire()`, `vwire()`) -- the wiring helpers `hwire()`/`vwire()`
are shared by `sampling-frontend-wells` and `sampling-frontend`, which both
build met1/met2 wires and landing pads the same way (this module's own
`WIRE_UM` only supplies their default width; each consumer keeps its own
module-level `WIRE_UM`, byte-identical to this one, for its other uses).
`within()` for the comparator's greedy track router remains a genuine,
sub-block-specific extension and stays defined on that sub-block's own
`Rect` subclass, not here.

Also houses the tap/well-tie structure all three consumers draw the same
way: `tap_shapes()` (the shared shape-construction core -- tap+li1 rects
plus a licon1 column, at the `L_TAP`/`L_LICON`/`L_LI1`/`LICON_PITCH_UM`
layers/pitch defined here), and the `sampling-frontend`/
`sampling-frontend-wells` pair's own `_assert_well_isolation()` and
`_assert_column_pitch()` build-time invariant checks (byte-identical between
those two consumers; `comparator` does not use either check). Each consumer
still owns its own `tap_shapes()` *wrapper*: `comparator`'s returns a `Pin`,
the other two return `(shapes, cx, cy)` -- see `tap_shapes()`'s own
docstring below for why the shared core stays shape-only.

Since issue #909 it also houses the Row-1 PFET n-well island floorplan,
`floorplan_pfet_well_islands()` -- "walk the device table in domain order,
place each domain's blocks on a fixed pitch, and size one n-well rectangle
plus one tap strip per domain" -- which `sampling-frontend-wells` (issue
#122's own recipe) and `sampling-frontend` Row 1 held byte-identical copies
of, differing only in the function name, the docstring, and whether the
shared `_pfet_devices` table was spelled `PFET_DEVICES` or aliased to
`DEVICES`. The nine constants that plan was the only reader of in each
consumer (`WELL_MARGIN_UM`, `WELL_TAP_MARGIN_UM`, `WELL_BELOW_UM`,
`WELL_ABOVE_UM`, the four `TAP_{X,Y}{0,1}_UM` and `BLOCK_PITCH_UM`) moved
here with it; `WELL_GAP_UM` deliberately did NOT, and is a parameter
instead, because each consumer has three readers of its own copy -- the same
`WIRE_UM`-style retention this header records above. Each flow keeps its own
public wrapper name (`floorplan()` / `floorplan_row1()`) so nothing else in
either module moved. `layout/halflsb-offset/bin/build_layout.py` carries
seven of those constants at the same values but plans a different,
group-based floorplan with no per-domain tap net, and has other local
readers of them, so it is deliberately not a consumer of this function.

Since issue #495 it also houses the metal-stack layer table and
`step_down_to_met1()` -- the "walk any generator port down to met1 before
routing it" via-stack emitter `layout/sampling-frontend/bin/build_layout.py`
worked out empirically (three layer cases, each with a DRC finding behind
it) and `layout/halflsb-offset/bin/build_layout.py` needs verbatim, because
both compose `klt gen cap_array` MiM units (met3 bottom-plate / met4
top-plate ports) alongside `klt gen mos_array` devices (li1 S/G/D ports).

`layout/sampling-frontend/bin/build_layout.py` kept its own byte-identical
`_step_down_to_met1` for a while after that extraction, because that
function's output is the *drawn geometry* behind that flow's committed
DRC-clean / LVS-match record and this repo's records are append-only, so
re-pointing it belonged with that flow's next re-run rather than with a
sibling block's first one. Issue #845 did the fold-in once that flow had
re-run: this is now the only copy, and both consumers call it. The
equivalence test that held the two copies honest meanwhile
(`sim/tests/test_geometry_common_shared_helpers.py`) had already proved the
fold-in a no-op for drawn geometry; what remains there pins THIS emitter's
own output, layer case by layer case, rather than two copies against each
other.
"""
from __future__ import annotations

DBU = 1000  # nm per um

# Default `hwire()`/`vwire()` width -- met1/met2 wire + landing-pad width
# (m1.1/m2.1 minimum 0.14). Each consumer (`sampling-frontend-wells`,
# `sampling-frontend`) also keeps its own module-level `WIRE_UM` constant,
# byte-identical to this one, for its other uses elsewhere in that module
# (`Rect.centred()` calls, spacing minimums); this copy only fixes the
# `hwire()`/`vwire()` default so those two stay in lockstep.
WIRE_UM = 0.30


def nm(value_um: float) -> int:
    """Micrometres -> integer nanometres (the layout database unit)."""
    return int(round(value_um * DBU))


class Rect:
    """An axis-aligned rectangle in integer nanometres."""

    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @classmethod
    def um(cls, x0: float, y0: float, x1: float, y1: float) -> "Rect":
        return cls(nm(x0), nm(y0), nm(x1), nm(y1))

    @classmethod
    def centred(cls, cx: float, cy: float, w: float, h: float) -> "Rect":
        return cls(nm(cx - w / 2), nm(cy - h / 2), nm(cx + w / 2), nm(cy + h / 2))

    def as_um(self) -> list[float]:
        return [self.x0 / DBU, self.y0 / DBU, self.x1 / DBU, self.y1 / DBU]

    @classmethod
    def hwire(cls, xa: float, xb: float, y: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (xa, xb) if xa <= xb else (xb, xa)
        return cls.um(lo - width / 2, y - width / 2, hi + width / 2, y + width / 2)

    @classmethod
    def vwire(cls, x: float, ya: float, yb: float, width: float = WIRE_UM) -> "Rect":
        lo, hi = (ya, yb) if ya <= yb else (yb, ya)
        return cls.um(x - width / 2, lo - width / 2, x + width / 2, hi + width / 2)


# --- tap/well-tie structure: layers + pitch, shared by all three consumers ---
L_TAP = (65, 44)
L_LICON = (66, 44)
L_LI1 = (67, 20)
LICON_PITCH_UM = 0.60

# --- metal stack: layers + cut/pad sizing, for `step_down_to_met1()` ---------
# sky130A GDS numbers, as klt's own curated deck names them. Each consumer that
# also uses one of these layers for its OWN wiring keeps its own module-level
# copy of just that name, byte-identical to this one, exactly the way `WIRE_UM`
# above is already carried twice -- `layout/sampling-frontend/bin/build_layout.py`
# keeps L_MCON/L_MET1/L_VIA1/L_MET2 for its own columns, tracks and taps. The
# met3/met4 stack layers below are drawn only by `step_down_to_met1`, so this is
# their only definition.
L_MCON = (67, 44)
L_MET1 = (68, 20)
L_VIA1 = (68, 44)
L_MET2 = (69, 20)
L_VIA2 = (69, 44)
L_MET3 = (70, 20)
L_VIA3 = (70, 44)
L_MET4 = (71, 20)

MCON_UM = 0.17
VIA1_UM = 0.15  # via1 square side (via1.width min 0.15), proven DRC-clean
# against met1/met2.enclosing.via.1's 0.055um threshold with a 0.30um pad.
VIA23_UM = 0.20  # via2/via3 square side (via2/via3.width min 0.20 -- a
# DIFFERENT, larger minimum than via1's 0.15; found directly building
# `layout/sampling-frontend/`, as via2.width.1 violations at 0.15).
# via.5a/m2.5 (klt 0.8.0 `*.enclosing_adjacent.via.1`): a via1 needs >= 0.085 um
# of metal on two ADJACENT sides; a 0.30 um wire/pad leaves 0.075 um on each.
VIA1_SITE_PAD_UM = 0.32  # = VIA1_UM + 2 * 0.085: met1/met2 pad at every via1 site
STACK_PAD_UM = 0.42  # landing pad for a stacked via cut (the same pad size
# `klt gen`'s own gate_contact uses), so a 0.20um via2/via3 lands with
# >= 0.11um enclosure on every side.
MET3_ISLAND_PAD_UM = 0.50  # a met3 pad that is the ONLY met3 shape at its own
# (x, y) has to satisfy sky130A's met3 MINIMUM-AREA rule (`m3.6`, 0.240um^2,
# from the pinned PDK's own libs.tech/klayout/drc/sky130A_mr.drc) on its own;
# a STACK_PAD_UM square is 0.1764um^2, below it and invisible to `klt drc`,
# whose curated sky130 deck carries no `area`-kind rule (issue #326; fixed
# upstream by klayout-tools#1989, not yet released). 0.50^2 = 0.25um^2 clears
# it. Verified by `docs/chipalooza/measure_metal_min_area.py`, which `klt drc`
# cannot replace. Each consumer's own met4 escape margin must still clear
# met3.space (0.30um) from the bottom plate's top edge to this wider pad's
# near edge -- `layout/sampling-frontend/`'s CAP_MET4_ESCAPE_MARGIN_UM (0.80)
# leaves 0.80 - 0.25 = 0.55um, comfortably over it.
MET3_VIA_INSET_UM = 0.20  # a `cap_array` *_BOT port's reported x sits right AT
# the bottom plate's own edge, so landing a via2 there pokes past met3's
# boundary and fails met3.enclosing.via2. Step the landing this far INTO the
# plate instead.


def tap_shapes(spec: dict, licon_um: float) -> list[tuple[tuple[int, int], "Rect"]]:
    """Shared core of one tap/well-tie structure: tap+li1 strip, licon1 column.

    ``spec`` gives the drawn rectangle's ``x0``/``x1``/``y0``/``y1`` (um);
    ``licon_um`` is the licon1 square side each consumer already sizes
    locally (their own module-level ``LICON_UM``, unchanged by this
    extraction -- it is not one of the layer/pitch constants above, since a
    future consumer could reasonably size its own licon1 cuts differently).

    Returns the shape list only -- deliberately not a `(shapes, cx, cy)` or
    `(shapes, Pin)` tuple, because the three consumers disagree on what else
    to return: `layout/comparator/bin/build_layout.py`'s own `tap_shapes()`
    wrapper builds a `Pin` from these shapes plus `spec`, while
    `layout/sampling-frontend/bin/build_layout.py` and
    `layout/sampling-frontend-wells/bin/build_layout.py`'s wrappers each
    return `(shapes, cx, cy)` floats instead. Each wrapper computes its own
    return contract from `spec` (which already carries `x0`/`x1`/`y0`/`y1`)
    rather than this shared core guessing which flavour to produce.
    """
    x0, x1, y0, y1 = spec["x0"], spec["x1"], spec["y0"], spec["y1"]
    shapes: list[tuple[tuple[int, int], "Rect"]] = [
        (L_TAP, Rect.um(x0, y0, x1, y1)),
        (L_LI1, Rect.um(x0, y0, x1, y1)),
    ]
    cx = (x0 + x1) / 2
    y = y0 + LICON_PITCH_UM / 2
    while y + LICON_PITCH_UM / 2 <= y1 + 1e-9:
        shapes.append((L_LICON, Rect.centred(cx, y, licon_um, licon_um)))
        y += LICON_PITCH_UM
    return shapes


class BuildError(RuntimeError):
    """A `build_layout.py` script's own build-time invariant was violated.

    Shared by `layout/sampling-frontend/bin/build_layout.py`,
    `layout/sampling-frontend-wells/bin/build_layout.py` (both raised this
    same, byte-identical exception class locally before this extraction) and
    `layout/halflsb-offset/bin/build_layout.py`;
    `layout/comparator/bin/build_layout.py` does not use it. Defined above
    `step_down_to_met1()`, which raises it.
    """


def step_down_to_met1(
    shapes: list[tuple[tuple[int, int], "Rect"]],
    x: float,
    y: float,
    layer: tuple[int, int],
    direction: float,
    met4_escape_y: float | None = None,
) -> tuple[float, float]:
    """Emit whatever via stack reaches met1 from ``layer``, and return the
    **effective** (x, y) the caller should treat as the pin's location from
    here on (usually the input point unchanged; see the ``L_MET3`` and
    ``L_MET4`` cases).

    Why every pin -- not just an li1 one -- ends up on met1: a net's met2
    track is one long horizontal rectangle spanning every column x that net
    touches. If a *different* net's riser also rode on met2 below its own
    track (which every cap-originated pin would, absent this rule, since it
    starts on met2 already), it would physically cross every lower-numbered
    net's met2 track at whatever x it shares with them -- an unconditional
    short between two unrelated nets, on the very layer that carries the whole
    track scheme. Met1 has no such hazard: it carries nothing but per-pin
    columns, so any column may freely underpass any net's met2 track.

    Extracted verbatim (issue #495) from
    `layout/sampling-frontend/bin/build_layout.py`'s own
    `_step_down_to_met1`, whose geometry that flow's committed record was
    drawn with; issue #845 folded that copy in, so this is the one emitter
    both consumers now call -- see this module's header for that staging and
    for what pins this function's output today.
    """
    if layer == L_LI1:
        shapes.append((L_MCON, Rect.centred(x, y, MCON_UM, MCON_UM)))
        return x, y
    if layer == L_MET3:
        # A `cap_array` *_BOT port reports its position AT the bottom plate's
        # own edge (direction 180 => the plate's left edge is x=0 in the
        # block's local frame) -- landing a via2 exactly there would poke past
        # met3's own boundary. Shift the via into the plate (direction 180
        # faces -x, so "into the plate" is +x) by MET3_VIA_INSET_UM; the thin
        # met3 strip between the reported edge and the via is already part of
        # the same bottom-plate conductor, so no extra wire bridges it.
        if direction == 180.0:
            x = x + MET3_VIA_INSET_UM
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        # The FINAL met1 pad, unlike the via2/via3 landing pads above, only has
        # to enclose via1 (0.15um) -- WIRE_UM (0.30) already clears that with
        # margin, and matching it to the jog wire's own width avoids a corner
        # notch a wider STACK_PAD_UM pad would leave between itself and the
        # (narrower) hwire/riser, which read back as met1.space.1 when first
        # built that way.
        shapes.append((L_MET1, Rect.centred(x, y, VIA1_SITE_PAD_UM, VIA1_SITE_PAD_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    if layer == L_MET4:
        # A `cap_array` *_TOP port's own via3 + local met3 landing sit DIRECTLY
        # ABOVE the bottom plate's own met3 sheet, which -- being a PLATE --
        # covers the unit's ENTIRE footprint. Adding a second via3/met3 pad at
        # the port's own (x, y) lands squarely inside that sheet and SHORTS the
        # two plates together (measured while building
        # `layout/sampling-frontend/`: `klt extract` reported the top- and
        # bottom-plate nets merged into one). There is no offset inside the
        # cell's footprint where a new met3 shape is safe.
        #
        # Fix: ride MET4 (which the bottom plate never touches) straight up and
        # OUT of the cell's footprint first -- `met4_escape_y`, past the unit's
        # own bbox top, supplied by the caller -- and only step down to
        # met3/met2/met1 once clear of it.
        if met4_escape_y is None:
            raise BuildError("L_MET4 port requires met4_escape_y")
        shapes.append((L_MET4, Rect.vwire(x, y, met4_escape_y)))
        # An explicit landing pad at the escape point: the vertical wire alone
        # only encloses via3 in x, not y (it ends exactly AT met4_escape_y, so
        # via3's own half-width above that point would poke past the wire's own
        # end -- a met4.enclosing.via3.1 violation found directly).
        shapes.append((L_MET4, Rect.centred(x, met4_escape_y, STACK_PAD_UM, STACK_PAD_UM)))
        y = met4_escape_y
        # This met3 pad is the whole met3 shape at this point -- via3 lands on
        # it from above, via2 leaves it from below, no met3 wire touches it --
        # so it satisfies m3.6 on its own: MET3_ISLAND_PAD_UM, not
        # STACK_PAD_UM (issue #326).
        shapes.append((L_MET3, Rect.centred(x, y, MET3_ISLAND_PAD_UM, MET3_ISLAND_PAD_UM)))
        shapes.append((L_VIA3, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET2, Rect.centred(x, y, STACK_PAD_UM, STACK_PAD_UM)))
        shapes.append((L_VIA2, Rect.centred(x, y, VIA23_UM, VIA23_UM)))
        shapes.append((L_MET1, Rect.centred(x, y, VIA1_SITE_PAD_UM, VIA1_SITE_PAD_UM)))
        shapes.append((L_VIA1, Rect.centred(x, y, VIA1_UM, VIA1_UM)))
        return x, y
    raise BuildError(f"no met1 step-down rule for layer {layer!r}")


# --- Row-1 PFET n-well island floorplan: its constants, then the plan -------
# Every constant below has exactly ONE reader -- `floorplan_pfet_well_islands`
# -- in each consumer, which is why they moved here with it (issue #909).
#: n-well margin around a domain's device blocks and its tap.
WELL_MARGIN_UM = 0.30
#: Left margin of each domain's n-well, reserved for the tap column.
WELL_TAP_MARGIN_UM = 2.00
#: n-well extent below / above the device row.
WELL_BELOW_UM = 2.40
WELL_ABOVE_UM = 0.40

#: Tap strip geometry, in each domain's left margin (x relative to the
#: domain's n-well x0), below the device row.
TAP_X0_UM = 0.40
TAP_X1_UM = 1.00
TAP_Y0_UM = -1.80
TAP_Y1_UM = -0.60

#: Device block pitch along the row.
BLOCK_PITCH_UM = 3.20


def floorplan_pfet_well_islands(
    blocks: dict[str, dict],
    devices: list[tuple],
    domain_tap_net: dict[str, str],
    well_gap_um: float,
) -> tuple[dict, list[dict]]:
    """Place every device block and size the three n-well islands.

    Returns ``(origins, domains)`` where ``origins`` maps block id ->
    ``{"x": .., "y": ..}`` (the `klt gen-compose` placement) and ``domains``
    is one entry per n-well island, in left-to-right order -- the shape
    :func:`_assert_well_isolation` below checks, and the shape each consumer
    draws its island/tap rectangles and tap routing from.

    ``devices`` is `_pfet_devices.PFET_DEVICES` and ``domain_tap_net`` its
    domain -> tap-net map, both passed in rather than imported here because
    each flow's own `gen_blocks.py` is the re-export point its siblings read
    that table from (see that module's note on its deliberate
    ``DOMAIN_TAP_NET`` re-export, issues #251/#383/#394). A domain is a
    *contiguous x range* in ``devices`` order, which is what lets one drawn
    rectangle per domain merge exactly that domain's device wells.

    ``well_gap_um`` is a parameter rather than a constant here for the same
    reason ``WIRE_UM`` above is carried twice: each consumer has three
    readers of its own ``WELL_GAP_UM`` -- this plan's cursor advance, its
    :func:`_assert_well_isolation` call, and the drawn separation it reports
    in its own summary document -- so that one stays local to each flow,
    while the nine single-reader constants above moved here with this
    function.

    Extracted (issue #909) from `layout/sampling-frontend-wells/bin/
    build_layout.py`'s own ``floorplan()`` -- the copy that already carried
    this docstring -- of which `layout/sampling-frontend/bin/build_layout.py`
    held a byte-identical second copy as ``floorplan_row1()``, under a
    section comment that said so ("Row 1: PFETs, unchanged from
    layout/sampling-frontend-wells/"). The two differed only in the function
    name, that docstring, and whether the shared device table was spelled
    ``PFET_DEVICES`` or ``DEVICES`` -- the latter being
    `_pfet_devices.PFET_DEVICES` under an ``as`` alias, so the same object.
    Both flows re-emitted their committed ``draw.request.json`` /
    ``compose.request.json`` / summary documents byte-identically across the
    fold-in, so no drawn geometry moved and neither flow's append-only record
    needed re-minting; what pins this emitter from here on is
    `sim/tests/test_geometry_common_shared_helpers.py`, asserting THIS
    function's own origins/island/tap output rather than two copies against
    each other -- the discipline that file records for
    :func:`step_down_to_met1`.
    """
    origins: dict[str, dict[str, float]] = {}
    domains: list[dict] = []

    cursor = 0.0
    ordered_domains: list[str] = []
    for _bid, _name, domain, *_rest in devices:
        if domain not in ordered_domains:
            ordered_domains.append(domain)

    for domain in ordered_domains:
        members = [row[0] for row in devices if row[2] == domain]
        well_x0 = cursor
        x = well_x0 + WELL_TAP_MARGIN_UM
        for block_id in members:
            origins[block_id] = {"x": x, "y": 0.0}
            x += BLOCK_PITCH_UM
        last = members[-1]
        well_x1 = origins[last]["x"] + blocks[last]["bbox"]["x1"] + WELL_MARGIN_UM
        top = max(blocks[b]["bbox"]["y1"] for b in members)
        domains.append(
            {
                "id": domain,
                "net": domain_tap_net[domain],
                "members": members,
                "well": {
                    "x0": well_x0,
                    "y0": -WELL_BELOW_UM,
                    "x1": well_x1,
                    "y1": top + WELL_ABOVE_UM,
                },
                "tap": {
                    "x0": well_x0 + TAP_X0_UM,
                    "x1": well_x0 + TAP_X1_UM,
                    "y0": TAP_Y0_UM,
                    "y1": TAP_Y1_UM,
                },
            }
        )
        cursor = well_x1 + well_gap_um

    return origins, domains


def _assert_well_isolation(domains: list[dict], well_gap_um: float) -> None:
    """Every pair of adjacent n-well islands must clear ``nwell.2a`` with margin.

    Checked here as well as by `klt drc --deck sky130` (nwell.space.1, as of
    klt 0.4.0) on the finished GDS: a build-time failure names the offending
    pair, a DRC failure only names a coordinate.
    """
    for a, b in zip(domains, domains[1:]):
        gap = b["well"]["x0"] - a["well"]["x1"]
        if gap < well_gap_um - 1e-9:
            raise BuildError(
                f"n-well islands {a['id']!r} and {b['id']!r} are {gap:.3f} um "
                f"apart, below the drawn separation {well_gap_um} um"
            )


def _assert_column_pitch(columns: dict[float, str], minimum: float) -> None:
    """No two met1 columns may come closer than a wire width + met1 spacing.

    The floorplan constants make this true, but a device-size change (a wider
    W, a longer L) moves the landing pads and could silently break it -- so
    it is re-derived from the *actual* generated port geometry on every
    build rather than asserted once in a comment.
    """
    xs = sorted(columns)
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa < minimum - 1e-9:
            raise BuildError(
                f"met1 columns for nets {columns[xa]!r} (x={xa:.3f}) and "
                f"{columns[xb]!r} (x={xb:.3f}) are {xb - xa:.3f} um apart, "
                f"below the {minimum:.2f} um wire+space pitch"
            )

#!/usr/bin/env python3
"""Back-end real-estate and tie-resistance probe for the on-die decoupling
capacitors (issue #440, DR-017).

Answers the two questions issue #440 asks about DR-017's placement that no
verdict in `bin/run-flow.sh` can answer, each with a measurement rather than an
argument:

    1. **Was the met3/met4 real estate DR-017's Decision §3 budget assumes
       actually free?** DR-017 allocates 8798.44 um^2 of `capm` -- 8.14 % of the
       composed die's bounding box -- on the argument that `cap_mim_m3_1` is a
       back-end device (met3/met4 plates with `capm` between them) and can
       therefore be drawn *over* sub-blocks that route below met3. That
       argument was never checked against the composed die's own back-end
       occupancy; its own "Open items" says so. This script measures that
       occupancy on a BASELINE record (a GDS from before the placement), grows
       it by the placement keep-out, and reports whether each of
       `build_layout.DECAP_OFFSETS`' footprints lands in clear field.

    2. **How much series resistance does each tie add between a capacitor and
       the rail it decouples?** DR-017's own measured benefit was obtained with
       an IDEAL capacitor, and its closing open item names exactly this series
       resistance as the one thing that can erode it. `klt drc` grades shapes
       and `klt erc` is a connectivity model with no resistance in it, so
       neither says anything about it. This script builds a lumped DC ladder
       for each of the four ties from the SAME `build_layout` constants
       `decoupling_caps()` draws from, evaluates it with the PDK's own
       `res_typical__cap_typical.spice` sheet/via resistances, and cross-checks
       every segment against the rectangles the graded record actually drew.

Why the cross-check matters
---------------------------
A resistance model assembled from a module's constants is only worth reading if
the module really drew those segments. So every wire segment in the ladder is
looked up in the record's own `draw.request.json` -- the file `klt draw` was
handed -- and a segment with no matching rectangle is a hard failure, not a
warning. That is what stops this script from becoming a plausible-looking
second source of truth that has quietly drifted from the layout.

What it deliberately does NOT model
-----------------------------------
* **The plate's own distributed resistance.** A 46.9 um met3 plate fed from one
  edge via is not a lumped node; the ladder here stops at the via into the
  plate. The omission is optimistic, and bounded: met3 at `rm3` across 46.9 um
  of 46.9 um-wide plate is one square, 0.047 ohm -- three orders of magnitude
  below the via that feeds it.
* **Inductance.** Nothing here is a loop model. At the package resonance the
  ladder's own R is what sets the pair's Q, which is the number DR-017's
  ideal-cap measurement is missing; the ties' own L is smaller than the
  1.914 nH `DR-015-package-parasitic-assumption.md` already puts in series and
  is not separable without extraction.
* **Any claim about whether the bounce target is met.** That is a simulation
  question, measured in `sim/supply-impedance-sensitivity/`. This script
  reports the ESR the placement costs; whether that ESR matters is read off
  against the reactance it is compared to, below.

Usage
-----
    layout/sar-adc-top/bin/probe-decap-sites.py \
        --record layout/sar-adc-top/reports/<tag> \
        --baseline layout/sar-adc-top/reports/<pre-placement tag> \
        [--format text|json]

`--baseline` is optional: without it, question 1 is reported against the
record's own GDS instead, which can only say "the units are there", not "the
field they went into was free". The README's numbers are the two-argument form.

`bin/run-flow.sh` runs this automatically as step 7b, into the record's own
`decap-ties.json`, and fails the flow if the resistance model no longer matches
the drawn geometry. It passes the record `reports/LATEST` named *before* the run
as `--baseline`, which is only meaningful while that record predates the
decoupling placement -- a condition this script DETECTS (a `capm` plate already
inside one of the sites) rather than assumes, reporting
`baseline_predates_placement: false` and an inconclusive arm rather than a false
CLASH verdict. Name a specific earlier record with
`DECAP_BASELINE_RECORD=<record-id> bin/run-flow.sh`, which is how the committed
record's own `decap-ties.json` was minted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_layout as bl  # noqa: E402

try:
    import klayout.db as db
except ImportError:  # pragma: no cover - the flow's venv always has it
    db = None

# --------------------------------------------------------------------------- #
# The layers a `cap_array` unit and its ties actually consume. Identical to
# `build_layout.DECAP_KEEPOUT_LAYERS` plus a name for each, because a report
# that prints `(70, 20)` is a report nobody reads.
# --------------------------------------------------------------------------- #
BACK_END_LAYERS = {
    "met3": bl.MET3,
    "via3": bl.VIA3,
    "met4": bl.MET4,
    "via4": bl.VIA4,
    "met5": bl.MET5,
    "capm": bl.CAPM,
}

#: The PDK parameter file every sheet/via resistance below is read out of, so
#: no resistivity in this script is a typed-in constant. Relative to the PDK
#: root `klt` itself resolves (`$PDK_ROOT/sky130A`, or the `~/.volare` /
#: `~/.ciel` search root the flow's own provenance records).
PDK_RES_FILE = "libs.tech/ngspice/r+c/res_typical__cap_typical.spice"

#: `.param` name in that file for each layer's sheet resistance (ohm/square)
#: and each via's per-cut resistance (ohm/cut).
RSH_PARAM = {bl.MET1: "rm1", bl.MET2: "rm2", bl.MET3: "rm3", bl.MET4: "rm4", bl.MET5: "rm5"}
RVIA_PARAM = {
    (bl.MET2, bl.MET3): "rcvia2",
    (bl.MET3, bl.MET4): "rcvia3",
    (bl.MET4, bl.MET5): "rcvia4",
}


def find_pdk_root() -> Path | None:
    """The same search roots this flow's own records name for sky130A."""
    import os

    candidates = []
    if os.environ.get("PDK_ROOT"):
        candidates.append(Path(os.environ["PDK_ROOT"]) / "sky130A")
    home = Path.home()
    candidates += [home / ".volare" / "sky130A", home / ".ciel" / "sky130A"]
    for root in candidates:
        if (root / PDK_RES_FILE).is_file():
            return root
    return None


def read_pdk_resistances(pdk_root: Path) -> dict[str, float]:
    """Every `.param <name>=<value>` in the typical R+C corner file."""
    text = (pdk_root / PDK_RES_FILE).read_text()
    out: dict[str, float] = {}
    for match in re.finditer(r"^\+\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+0-9.eE]+)\s*$",
                             text, re.MULTILINE):
        try:
            out[match.group(1)] = float(match.group(2))
        except ValueError:
            continue
    return out


# --------------------------------------------------------------------------- #
# Question 1: back-end occupancy, and whether the placed footprints went into
# clear field.
# --------------------------------------------------------------------------- #
def occupancy(gds_path: Path) -> dict:
    """Per-layer shape count and merged area for every back-end layer, plus the
    composed bounding box the shares are taken against."""
    if db is None:
        raise SystemExit("probe-decap-sites.py: klayout.db is not importable")
    layout = db.Layout()
    layout.read(str(gds_path))
    top = layout.top_cell()
    dbu = layout.dbu
    box = top.dbbox()
    die_um2 = box.width() * box.height()
    per_layer = {}
    for name, (lnum, dtype) in BACK_END_LAYERS.items():
        index = layout.find_layer(lnum, dtype)
        if index is None:
            per_layer[name] = {"shapes": 0, "area_um2": 0.0, "share_of_die": 0.0}
            continue
        region = db.Region(top.begin_shapes_rec(index))
        shapes = region.count()
        region.merge()
        area = region.area() * dbu * dbu
        per_layer[name] = {
            "shapes": shapes,
            "area_um2": round(area, 3),
            "share_of_die": round(100.0 * area / die_um2, 3),
        }
    return {
        "gds": _repo_relative(gds_path),
        "top_cell": top.name,
        "bbox_um": [box.left, box.bottom, box.right, box.top],
        "bbox_w_h_um": [round(box.width(), 3), round(box.height(), 3)],
        "die_um2": round(die_um2, 3),
        "layers": per_layer,
    }


def site_clearance(gds_path: Path, keepout_um: float) -> dict:
    """For each placed unit's footprint: how much back-end geometry in
    `gds_path` falls inside it, grown by `keepout_um`.

    On a BASELINE (pre-placement) GDS a zero here is the finding: the site was
    free, so the allocation displaced nothing. On the record's own GDS the same
    footprints are of course occupied -- by the units themselves -- which is
    why the README's numbers use `--baseline`.
    """
    layout = db.Layout()
    layout.read(str(gds_path))
    top = layout.top_cell()
    dbu = layout.dbu
    occ = db.Region()
    for lnum, dtype in BACK_END_LAYERS.values():
        index = layout.find_layer(lnum, dtype)
        if index is not None:
            occ += db.Region(top.begin_shapes_rec(index))
    occ.merge()
    grown = occ.sized(int(round(keepout_um / dbu)))
    grown.merge()
    sites = {}
    for block in bl.DECAP_OFFSETS:
        x0, y0, x1, y1 = bl.global_bbox(block)
        box = db.Region(db.Box(*[int(round(v / dbu)) for v in (x0, y0, x1, y1)]))
        clash = box & grown
        sites[block] = {
            "footprint_um": [x0, y0, x1, y1],
            "clash_polygons": clash.count(),
            "clash_area_um2": round(clash.area() * dbu * dbu, 3),
            "clear": clash.count() == 0,
        }
    # A baseline that ALREADY carries the units cannot answer "was this field
    # free?" -- its own plates fill every site. Detected rather than assumed, so
    # a run handed the wrong baseline reports an inconclusive arm instead of a
    # false CLASH verdict: `capm` inside a site's own footprint is the tell,
    # because nothing but a MiM plate draws that layer up here.
    capm_index = layout.find_layer(*BACK_END_LAYERS["capm"])
    capm = db.Region(top.begin_shapes_rec(capm_index)) if capm_index is not None else db.Region()
    occupied_by_a_plate = [
        block
        for block in bl.DECAP_OFFSETS
        if (capm & db.Region(db.Box(*[int(round(v / dbu))
                                      for v in bl.global_bbox(block)]))).count()
    ]
    return {
        "gds": _repo_relative(gds_path),
        "keepout_um": keepout_um,
        "baseline_predates_placement": not occupied_by_a_plate,
        "sites_already_holding_a_capm_plate": occupied_by_a_plate,
        "sites": sites,
    }


def free_corridors(gds_path: Path, keepout_um: float) -> dict:
    """The two rectangles the placement was chosen out of, re-measured.

    These are not a search result -- they are the two claims
    `build_layout.DECAP_OFFSETS`' own comment makes about where the free field
    is, restated here so they are checkable rather than asserted. Each is
    reported with the clash area against back-end geometry grown by the
    keep-out, and with how many 47.9 x 48.82 um units fit along each axis.
    """
    layout = db.Layout()
    layout.read(str(gds_path))
    top = layout.top_cell()
    dbu = layout.dbu
    occ = db.Region()
    for lnum, dtype in BACK_END_LAYERS.values():
        index = layout.find_layer(lnum, dtype)
        if index is not None:
            occ += db.Region(top.begin_shapes_rec(index))
    occ.merge()
    grown = occ.sized(int(round(keepout_um / dbu)))
    grown.merge()
    ux0, uy0, ux1, uy1 = bl.BBOX[next(iter(bl.DECAP_OFFSETS))]
    uw, uh = ux1 - ux0, uy1 - uy0
    out = {}
    for name, rect in CORRIDORS.items():
        box = db.Region(db.Box(*[int(round(v / dbu)) for v in rect]))
        clash = box & grown
        out[name] = {
            "rect_um": list(rect),
            "w_h_um": [round(rect[2] - rect[0], 3), round(rect[3] - rect[1], 3)],
            "clash_polygons": clash.count(),
            "clash_area_um2": round(clash.area() * dbu * dbu, 3),
            "units_across_x": int((rect[2] - rect[0]) // uw),
            "units_across_y": int((rect[3] - rect[1]) // uh),
        }
    return {"gds": _repo_relative(gds_path), "keepout_um": keepout_um,
            "unit_w_h_um": [uw, uh],
            "corridors": out}


#: The two free rectangles `build_layout.DECAP_OFFSETS`' own comment names, as
#: `(x0, y0, x1, y1)` in the composed frame. The east edge of each is the
#: composed die's own right edge (260.2) rather than a measured obstruction --
#: there is nothing east of these corridors at all on any back-end layer, which
#: is itself part of the finding.
CORRIDORS = {
    "analog (east of comparator, north of sampling_frontend)": (120.0, 139.5, 258.5, 219.5),
    "digital (east of seln_inverters, south of cdac_array)": (193.0, -165.0, 260.2, -6.0),
}


# --------------------------------------------------------------------------- #
# Question 2: the lumped DC ladder for each tie.
#
# Every segment below is assembled from the SAME `build_layout` constant
# `decoupling_caps()` / `decoupling_caps_digital()` draws it from -- never from
# a number typed in here -- and then looked up in the record's own
# `draw.request.json`. A `Wire` whose rectangle is not in that file is a hard
# failure: it means this model and the layout have diverged.
# --------------------------------------------------------------------------- #
class Wire:
    """One drawn metal run: `rsh * length / width` ohms."""

    def __init__(self, layer, x0, y0, x1, y1, w, note):
        self.layer, self.x0, self.y0, self.x1, self.y1, self.w = layer, x0, y0, x1, y1, w
        self.note = note

    def length(self) -> float:
        return abs(self.x1 - self.x0) + abs(self.y1 - self.y0)

    def ohms(self, res: dict[str, float]) -> float:
        return res[RSH_PARAM[self.layer]] * self.length() / self.w

    def rect(self) -> tuple[float, float, float, float]:
        """The rectangle `Canvas.wire()` draws for this run -- extended by half
        the width at BOTH ends, which is what that method does."""
        h = self.w / 2.0
        if abs(self.x0 - self.x1) < 1e-9:
            return (self.x0 - h, min(self.y0, self.y1) - h, self.x0 + h, max(self.y0, self.y1) + h)
        return (min(self.x0, self.x1) - h, self.y0 - h, max(self.x0, self.x1) + h, self.y0 + h)

    def describe(self, res) -> str:
        return (
            f"{_layer_name(self.layer)} {self.length():.3f} um / {self.w:.1f} um wide "
            f"= {self.length() / self.w:.2f} sq x {res[RSH_PARAM[self.layer]]} ohm/sq "
            f"= {self.ohms(res):.3f} ohm  ({self.note})"
        )


class Via:
    """One via stack level, `cuts` cuts in parallel."""

    def __init__(self, lo, hi, cuts, note):
        self.lo, self.hi, self.cuts, self.note = lo, hi, cuts, note

    def ohms(self, res: dict[str, float]) -> float:
        return res[RVIA_PARAM[(self.lo, self.hi)]] / self.cuts

    def describe(self, res) -> str:
        param = RVIA_PARAM[(self.lo, self.hi)]
        return (
            f"{_layer_name(self.lo)}<->{_layer_name(self.hi)} via, {self.cuts} cut(s) "
            f"= {res[param]} ohm / {self.cuts} = {self.ohms(res):.3f} ohm  ({self.note})"
        )


def _layer_name(layer: tuple[int, int]) -> str:
    for name, value in BACK_END_LAYERS.items():
        if value == layer:
            return name
    return {bl.MET1: "met1", bl.MET2: "met2"}.get(layer, str(layer))


def tie_ladders() -> dict[str, dict]:
    """One ladder per tie: a shared prefix, then one branch per unit.

    `R_tie = R_shared + (R_branch0 || R_branch1)` -- the resistance a lumped
    model of that domain sees looking from the rail into the parallel pair.
    """
    boxes = {block: bl.global_bbox(block) for block in bl.DECAP_OFFSETS}

    def bot_via_x(block: str) -> float:
        return boxes[block][0] + bl.DECAP_VIA2_INSET_UM

    def lead(block: str) -> tuple[float, float]:
        x, y, _layer = bl.global_pin(block, "C0_TOP")
        return x, y

    tap_x, _y, _n = bl.global_pin("comparator", "GND")
    vdd_x, _y, _n = bl.global_pin("comparator", "VDD")
    w = bl.DECAP_STRAP_W
    a_y = bl.DECAP_A_BOT_Y
    t_y = bl.DECAP_A_TOP_Y

    # Each digital rail's own centre-line y, re-derived the way
    # `digital_supply_rail()` does. The two rails are NOT at the same y (they
    # are 13.6 um apart -- `MET5_STRAP`'s own pitch), which is why this is
    # per-net; asserting the model against the drawn geometry is what caught
    # a first draft of this script using one y for both.
    rail_y = {net: _rail_centre_y(net) for net in bl.DIG_RAILS}

    ladders: dict[str, dict] = {
        "VDD (analog supply -> both top plates)": {
            "shared": [
                Wire(bl.MET4, vdd_x, t_y, lead("decap_a0")[0], t_y, w,
                     "met4 strap east from comparator.VDD's own column"),
            ],
            "branches": {
                "decap_a0": [
                    Wire(bl.MET4, lead("decap_a0")[0], t_y, lead("decap_a0")[0],
                         lead("decap_a0")[1] - bl.DECAP_TOP_OVERLAP_UM, w,
                         "met4 column down onto the unit's own top-plate lead"),
                    Via(bl.MET3, bl.MET4, 1, "the unit cell's OWN centre via3 into capm"),
                ],
                "decap_a1": [
                    Wire(bl.MET4, lead("decap_a0")[0], t_y, lead("decap_a1")[0], t_y, w,
                         "met4 strap on east to the far unit"),
                    Wire(bl.MET4, lead("decap_a1")[0], t_y, lead("decap_a1")[0],
                         lead("decap_a1")[1] - bl.DECAP_TOP_OVERLAP_UM, w,
                         "met4 column down onto the unit's own top-plate lead"),
                    Via(bl.MET3, bl.MET4, 1, "the unit cell's OWN centre via3 into capm"),
                ],
            },
        },
        "GND (analog return -> both bottom plates)": {
            "shared": [
                Via(bl.MET3, bl.MET4, 1, "riser off comparator.GND's own met4 stub"),
                Via(bl.MET2, bl.MET3, 1, "riser, met3 island down to met2"),
                Wire(bl.MET2, tap_x, a_y, bot_via_x("decap_a0"), a_y, w,
                     "met2 run east under the pair"),
            ],
            "branches": {
                "decap_a0": [Via(bl.MET2, bl.MET3, 1, "via2 up into the bottom plate")],
                "decap_a1": [
                    Wire(bl.MET2, bot_via_x("decap_a0"), a_y, bot_via_x("decap_a1"), a_y, w,
                         "met2 run on east to the far unit"),
                    Via(bl.MET2, bl.MET3, 1, "via2 up into the bottom plate"),
                ],
            },
        },
        "VPWR (digital supply -> both top plates)": {
            "shared": [
                Via(bl.MET4, bl.MET5, 1, "via4 down off the met5 rail"),
                Wire(bl.MET4, bl.DECAP_D_VIA4_X["VPWR"], rail_y["VPWR"],
                     lead("decap_d0")[0], rail_y["VPWR"], w,
                     "met4 strap east to the shared lead x"),
                Wire(bl.MET4, lead("decap_d0")[0], rail_y["VPWR"], lead("decap_d0")[0],
                     lead("decap_d0")[1], w, "met4 column north to the near unit's lead"),
            ],
            "branches": {
                "decap_d0": [
                    Via(bl.MET3, bl.MET4, 1, "the unit cell's OWN centre via3 into capm"),
                ],
                "decap_d1": [
                    Wire(bl.MET4, lead("decap_d0")[0], lead("decap_d0")[1],
                         lead("decap_d1")[0], lead("decap_d1")[1], w,
                         "met4 column on north to the far unit's lead"),
                    Via(bl.MET3, bl.MET4, 1, "the unit cell's OWN centre via3 into capm"),
                ],
            },
        },
        "VGND (digital return -> both bottom plates)": {
            "shared": [
                Via(bl.MET4, bl.MET5, 1, "via4 down off the met5 rail"),
                Via(bl.MET3, bl.MET4, 1, "riser, met4 pad down to its met3 island"),
                Via(bl.MET2, bl.MET3, 1, "riser, met3 island down to met2"),
                Wire(bl.MET2, bl.DECAP_D_VIA4_X["VGND"], rail_y["VGND"],
                     bot_via_x("decap_d0"), rail_y["VGND"], w,
                     "met2 run east to the plate x"),
            ],
            "branches": {
                "decap_d0": [Via(bl.MET2, bl.MET3, 1, "via2 up into the bottom plate")],
                "decap_d1": [
                    Wire(bl.MET2, bot_via_x("decap_d0"), rail_y["VGND"],
                         bot_via_x("decap_d0"),
                         boxes["decap_d1"][1] + bl.DECAP_VIA2_INSET_UM, w,
                         "met2 run north to the far unit"),
                    Via(bl.MET2, bl.MET3, 1, "via2 up into the bottom plate"),
                ],
            },
        },
    }
    return ladders


def _rail_centre_y(net: str) -> float:
    """`net`'s own met5 rail centre-line y -- the same band
    `digital_supply_rail()` draws its rectangle in, re-derived from
    `sar_sequencer`'s own strap table (the one `MET5_STRAP` entry that rail is
    anchored on) rather than by rebuilding the canvas.

    Per-net on purpose: `VPWR` and `VGND` are 13.6 um apart in y, so a single
    shared value silently mismodels one of the two return paths. That is not a
    hypothetical -- `verify_against_record()` rejected a first draft of this
    script that did exactly that.
    """
    (strap,) = bl.global_straps("sar_sequencer", net)
    return (strap[1] + strap[3]) / 2.0


def evaluate(ladders: dict[str, dict], res: dict[str, float]) -> dict:
    out = {}
    for tie, spec in ladders.items():
        shared = sum(seg.ohms(res) for seg in spec["shared"])
        branch = {name: sum(seg.ohms(res) for seg in segs)
                  for name, segs in spec["branches"].items()}
        inv = sum(1.0 / value for value in branch.values() if value > 0)
        parallel = 1.0 / inv if inv else float("inf")
        legs = {name: round(shared + value, 3) for name, value in branch.items()}
        out[tie] = {
            "shared_ohm": round(shared, 3),
            "branch_ohm": {k: round(v, 3) for k, v in branch.items()},
            "branches_parallel_ohm": round(parallel, 3),
            "tie_ohm": round(shared + parallel, 3),
            "per_leg_ohm": legs,
        }
    return out


def verify_against_record(ladders: dict[str, dict], record: Path) -> list[str]:
    """Every `Wire` in the ladder must be a rectangle the record's own
    `draw.request.json` carries. A missing one means this model is describing a
    layout that was not built."""
    request = json.loads((record / "draw.request.json").read_text())
    drawn = {(tuple(s["layer"]), tuple(round(v, 6) for v in s["rect_um"]))
             for s in request["shapes"]}
    problems = []
    for tie, spec in ladders.items():
        for seg in spec["shared"] + [s for segs in spec["branches"].values() for s in segs]:
            if not isinstance(seg, Wire):
                continue
            key = (seg.layer, tuple(round(v, 6) for v in seg.rect()))
            if key in drawn:
                continue
            # A run the model splits at a tap point is drawn by the layout as
            # ONE longer rectangle. Accept a drawn rectangle that contains this
            # segment's own rectangle on the same layer and has the same width.
            r = seg.rect()
            ok = any(
                layer == seg.layer
                and rect[0] - 1e-6 <= r[0] and r[2] <= rect[2] + 1e-6
                and rect[1] - 1e-6 <= r[1] and r[3] <= rect[3] + 1e-6
                and (abs((rect[3] - rect[1]) - (r[3] - r[1])) < 1e-6
                     or abs((rect[2] - rect[0]) - (r[2] - r[0])) < 1e-6)
                for layer, rect in drawn
            )
            if not ok:
                problems.append(
                    f"{tie}: no drawn rectangle on {_layer_name(seg.layer)} covers the "
                    f"model's segment {r} ({seg.note})"
                )
    return problems


#: This repo's root, from this script's own location (`layout/sar-adc-top/bin/`).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _repo_relative(path: Path) -> str:
    """`path` as a repo-relative string when it is inside this checkout.

    Absolute paths in a committed artefact name the machine that minted it, not
    the evidence it describes. `run-flow.sh` necessarily invokes this with
    absolute paths, so the normalisation happens here rather than at the call
    site.
    """
    resolved = Path(path).resolve()
    if resolved.is_relative_to(REPO_ROOT):
        return str(resolved.relative_to(REPO_ROOT))
    return str(path)


def reactance_crossover(r_ohm: float, c_farad: float) -> float:
    """The frequency at which the pair's own reactance equals `r_ohm` -- above
    it the tie, not the capacitor, sets the impedance."""
    import math

    return 1.0 / (2.0 * math.pi * r_ohm * c_farad)


def package_resonance(l_henry: float, c_farad: float) -> float:
    import math

    return 1.0 / (2.0 * math.pi * math.sqrt(l_henry * c_farad))


#: `DR-015-package-parasitic-assumption.md`'s own per-terminal package total,
#: quoted here only to say at WHAT frequency the ESR below is being compared to
#: the pair's reactance. Not a claim of this script's own.
DR015_PACKAGE_L_H = 1.914e-9


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", required=True, type=Path,
                        help="the graded record directory (reports/<tag>)")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="a PRE-placement record directory, for the free-field arm")
    parser.add_argument("--keepout-um", type=float, default=bl.DECAP_KEEPOUT_UM)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    pdk_root = find_pdk_root()
    if pdk_root is None:
        raise SystemExit(
            "probe-decap-sites.py: no sky130A PDK with "
            f"{PDK_RES_FILE} found (set PDK_ROOT)"
        )
    res = read_pdk_resistances(pdk_root)

    record_gds = args.record / "sar_adc_top.gds"
    base_gds = (args.baseline / "sar_adc_top.gds") if args.baseline else record_gds

    ladders = tie_ladders()
    problems = verify_against_record(ladders, args.record)
    evaluated = evaluate(ladders, res)

    c_domain = bl.DECAP_UNIT_C_F * (len(bl.DECAP_OFFSETS) // 2)
    domains = {
        "analog (VDD/GND)": ("VDD (analog supply -> both top plates)",
                             "GND (analog return -> both bottom plates)"),
        "digital (VPWR/VGND)": ("VPWR (digital supply -> both top plates)",
                                "VGND (digital return -> both bottom plates)"),
    }
    domain_esr = {
        name: round(sum(evaluated[tie]["tie_ohm"] for tie in ties), 3)
        for name, ties in domains.items()
    }
    f_res = package_resonance(DR015_PACKAGE_L_H, c_domain)

    result = {
        "schema_version": 1,
        # Repo-relative, always: `run-flow.sh` invokes this with absolute paths
        # (it works in `$OUT_DIR`), and a committed artefact must not carry the
        # ephemeral worktree it happened to be minted in -- the same reason
        # `erc-supply-spec.json` insists on repo-relative invocation paths.
        "record": _repo_relative(args.record),
        "baseline": _repo_relative(args.baseline) if args.baseline else None,
        # Home-relative, so a committed artefact carries the PDK's *location in
        # the standard search roots* rather than whichever machine minted it --
        # the same convention `klt`'s own provenance uses ("search root:
        # ~/.ciel").
        "pdk_root": ("~/" + str(pdk_root.relative_to(Path.home()))
                     if pdk_root.is_relative_to(Path.home()) else str(pdk_root)),
        "pdk_resistances": {k: res[k] for k in
                            list(RSH_PARAM.values()) + list(RVIA_PARAM.values())},
        "model_matches_drawn_geometry": not problems,
        "model_problems": problems,
        "occupancy_baseline": occupancy(base_gds),
        "occupancy_record": occupancy(record_gds),
        "site_clearance": site_clearance(base_gds, args.keepout_um),
        "free_corridors": free_corridors(base_gds, args.keepout_um),
        "ties": evaluated,
        "per_domain": {
            "capacitance_F": c_domain,
            "esr_ohm": domain_esr,
            "package_resonance_Hz": round(f_res, 1),
            "reactance_at_resonance_ohm": {
                name: round(1.0 / (2 * 3.141592653589793 * f_res * c_domain), 3)
                for name in domain_esr
            },
            "q_at_resonance": {
                name: round((1.0 / (2 * 3.141592653589793 * f_res * c_domain)) / esr, 3)
                for name, esr in domain_esr.items()
            },
            "esr_equals_reactance_Hz": {
                name: round(reactance_crossover(esr, c_domain), 1)
                for name, esr in domain_esr.items()
            },
        },
    }

    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=False))
        return 0 if not problems else 1

    print(f"probe-decap-sites.py -- record {args.record}")
    print(f"  PDK: {pdk_root}")
    print(f"  sheet/via resistances: "
          + ", ".join(f"{k}={res[k]}" for k in list(RSH_PARAM.values()) + list(RVIA_PARAM.values())))
    print()
    print("== Back-end occupancy ==")
    for label, key in (("baseline", "occupancy_baseline"), ("record", "occupancy_record")):
        occ = result[key]
        print(f"  {label}: {occ['gds']}")
        print(f"    bbox {occ['bbox_w_h_um'][0]} x {occ['bbox_w_h_um'][1]} um "
              f"= {occ['die_um2']} um^2")
        for name, entry in occ["layers"].items():
            print(f"    {name:5s} {entry['shapes']:5d} shapes  "
                  f"{entry['area_um2']:10.3f} um^2  {entry['share_of_die']:6.2f} % of die")
    print()
    print(f"== Placed sites vs BASELINE back-end geometry (keep-out "
          f"{args.keepout_um} um) ==")
    if not result["site_clearance"]["baseline_predates_placement"]:
        print("  INCONCLUSIVE: the baseline GDS already carries a capm plate at "
              + ", ".join(result["site_clearance"]["sites_already_holding_a_capm_plate"])
              + " -- a baseline that predates the placement is needed to say "
                "whether these sites were free.")
    for block, entry in result["site_clearance"]["sites"].items():
        verdict = "CLEAR" if entry["clear"] else f"CLASH {entry['clash_area_um2']} um^2"
        print(f"  {block:10s} {tuple(entry['footprint_um'])}  -> {verdict}")
    print()
    print("== Free corridors the placement was chosen out of ==")
    for name, entry in result["free_corridors"]["corridors"].items():
        print(f"  {name}")
        print(f"    {entry['rect_um']}  {entry['w_h_um'][0]} x {entry['w_h_um'][1]} um  "
              f"clash {entry['clash_area_um2']} um^2  "
              f"fits {entry['units_across_x']} x {entry['units_across_y']} units")
    print()
    print("== Tie series resistance (lumped DC, drawn conductor only) ==")
    if problems:
        print("  !! MODEL DOES NOT MATCH THE DRAWN GEOMETRY:")
        for problem in problems:
            print(f"     {problem}")
    else:
        print("  (every wire segment below verified present in the record's own "
              "draw.request.json)")
    for tie, spec in ladders.items():
        entry = evaluated[tie]
        print(f"  {tie}")
        for seg in spec["shared"]:
            print(f"    shared   {seg.describe(res)}")
        for name, segs in spec["branches"].items():
            for seg in segs:
                print(f"    {name:9s} {seg.describe(res)}")
        print(f"    -> shared {entry['shared_ohm']} ohm + "
              f"({' || '.join(f'{v}' for v in entry['branch_ohm'].values())}) "
              f"= {entry['tie_ohm']} ohm")
    print()
    per = result["per_domain"]
    print("== Per domain ==")
    print(f"  C = {per['capacitance_F'] * 1e12:.3f} pF")
    for name, esr in per["esr_ohm"].items():
        print(f"  {name:20s} ESR = {esr} ohm   "
              f"Q at the {per['package_resonance_Hz'] / 1e6:.1f} MHz DR-015 package "
              f"resonance = {per['q_at_resonance'][name]}   "
              f"ESR = Xc at {per['esr_equals_reactance_Hz'][name] / 1e9:.3f} GHz")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())

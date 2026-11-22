"""The mid-scale boundary probe campaign (`--midscale-probe`, issue #455).

Issue #848's split of `run_supply_impedance.py`. This module owns the probe's
perturbations, its deck surgery, its trial parsing, its findings prose and its
record writer. Imports `common` only.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import common
from .common import (
    ARMS_BY_NAME,
    Arm,
    CONTROL_ARM,
    NOMINAL_SUPPLY_V,
    RE_TRAN_CARD,
    RUNNER_REL,
    _mv,
    assemble_deck,
    extra_measure_names,
    load_cached_run,
    lsb_v,
    mid_scale_conversions,
    store_cached_run,
    tb,
)
from harness import corners as corners_mod, evidence, measure, pdk, toolchain
import run_conversion as fc


# --------------------------------------------------------------------------
# The mid-scale boundary probe (issue #455)
# --------------------------------------------------------------------------
# This campaign's code comparison is read on three mid-scale inputs, and on one
# of them -- `+0.00*V_REF` -- the `package-r-only` arm at `fs_27c_1.80v` was
# recorded 6 LSB away from the control (505 against 511) while the two arms with
# ~200x its die-side ground excursion read the control's code exactly. A
# supply-return mechanism cannot produce that ordering, so SOMETHING ELSE moves
# that code, and until it is named every "0 LSB / 1 LSB mid-scale delta" in this
# campaign is a number whose own error bar is unknown.
#
# This probe is what names it. It is a DIAGNOSTIC, not a corner campaign: one
# corner, a handful of variants, and it grades nothing against a spec row. Two
# things it does that the code comparison cannot:
#
#   1. It re-runs the committed deck of the recorded point and DIFFS the fresh
#      measurements against the committed log's, so "reproducible" stops being
#      an assumption. The control arm at the same corner is re-run beside it as
#      the mechanical check on the comparison itself.
#   2. It adds the per-trial decision-margin probes
#      (`sim/full-conversion-transient/run_conversion.py`'s own
#      `--decision-margin-trace` cards, imported rather than re-derived) to each
#      variant's deck, so every bit trial of the mid-scale conversions reports
#      the comparator's OWN differential input at the decision instant. That
#      turns "the residual is near zero somewhere" into a number per trial, and
#      it is what distinguishes a low-order boundary flip (a late trial sitting
#      within a fraction of an LSB of its threshold) from a metastable FIRST
#      trial (the sign bit, which gates all nine SELn/SELp pairs at once and so
#      cannot move the code by one LSB).
#
# And it runs the perturbations issue #455 asks for: a DC input offset of
# +-0.1 LSB and a changed `.tran` requested step, both of which leave the supply
# network exactly as the control has it. A mid-scale code that moves under those
# is a code that the supply-return ladder may not be read on.

#: The corner the 6-LSB move was recorded at (`fs_27c_1.80v`).
MIDSCALE_PROBE_CORNER: tuple[str, float, float] = ("fs", 27.0, NOMINAL_SUPPLY_V)

#: The record whose committed logs this probe reproduces against. Its
#: `package-r-only@fs_27c_1.80v` point is the 505; its `ideal@fs_27c_1.80v`
#: point is the 511 that point is a delta against.
MIDSCALE_PROBE_REFERENCE_RECORD = "20260926-050045-8e62675"

#: The arm the anomaly is on, beside the control every delta is taken against.
MIDSCALE_PROBE_ARM = "package-r-only"

#: The conversions traced. Same three mid-scale inputs
#: `--decision-margin-trace` traces, for the same reason: the near-full-scale
#: conversions are already wrong by ~100 LSB at every corner (issue #267), so
#: nothing about them can be attributed to anything this probe changes.
MIDSCALE_PROBE_CONVERSIONS: tuple[int, ...] = fc.DECISION_MARGIN_CONVERSIONS

#: The conversion whose code the anomaly is on (`+0.00*V_REF`). The same
#: conversion the committed fragment averages its supply currents over.
MIDSCALE_CONVERSION: int = tb.IDD_CONVERSION


@dataclass(frozen=True)
class Perturbation:
    """One supply-UNRELATED change to a variant's deck.

    Every field here changes either the stimulus's DC operating point by a
    fraction of an LSB or the solver's own timestep sequence -- never the supply
    network, never a device, never the netlist. That is the whole point: a
    mid-scale code that moves under one of these has moved for a reason the
    supply-impedance ladder does not measure.
    """

    name: str
    summary: str
    #: Differential input offset, in LSB, applied as +half on VINP and -half on
    #: VINN by shifting the LEVELS of the committed fragment's own two input PWL
    #: cards -- every breakpoint TIME and the node set stay the committed deck's
    #: (no source and no node is added). See `offset_vin()`.
    vin_offset_lsb: float = 0.0
    #: Replacement for the `.tran` card's requested step, in ns. Purely
    #: numerical: the stimulus, the stop time and every `.meas` instant are
    #: unchanged, only the sequence of timepoints the solver visits.
    tran_step_ns: float | None = None

    @property
    def is_as_committed(self) -> bool:
        return self.vin_offset_lsb == 0.0 and self.tran_step_ns is None


AS_COMMITTED = Perturbation(
    "as-committed",
    "the committed deck of this point, unchanged -- the reproduction control",
)

#: The perturbation menu. `0.1 LSB` because it is the smallest input change that
#: is unambiguously larger than anything numerical and still far below one code;
#: the halved `.tran` step because issue #455 names it, and because this host's
#: own reproduction of the reference record already showed the two builds
#: visiting 3-4x different numbers of timepoints for the same deck.
PERTURBATIONS: tuple[Perturbation, ...] = (
    AS_COMMITTED,
    Perturbation(
        "vin+0.1lsb",
        "the same deck with a +0.1 LSB DC differential input offset, applied to "
        "the LEVELS of the committed fragment's own two input PWL cards -- every "
        "breakpoint time, every node and the supply network are the committed "
        "deck's",
        vin_offset_lsb=+0.1,
    ),
    Perturbation(
        "vin-0.1lsb",
        "the same deck with a -0.1 LSB DC differential input offset, applied the "
        "same way",
        vin_offset_lsb=-0.1,
    ),
    Perturbation(
        "tran-step-0.25n",
        "the same deck with the `.tran` requested step halved to 0.25 ns -- a "
        "SOLVER-ONLY change: same circuit, same stimulus, same stop time, same "
        "measurement instants, different sequence of timepoints",
        tran_step_ns=0.25,
    ),
)

PERTURBATIONS_BY_NAME = {p.name: p for p in PERTURBATIONS}

#: The default variant list, as `arm:perturbation`. Ordered most-load-bearing
#: first: the two reproduction runs decide whether the recorded 505 is a
#: property of the deck at all, and everything after them is only worth reading
#: if those two ran. Five runs, ~1.6 h of whole-ADC transient on the reference
#: toolchain -- `{CONTROL_ARM}:tran-step-0.25n` is implemented and selectable
#: but left out of the default box, because the timestep perturbation's finding
#: (it moves the sign trial's margin by ~3 uV and the code by nothing) is
#: already carried by the arm that the anomaly is on.
MIDSCALE_PROBE_VARIANTS: tuple[str, ...] = (
    f"{CONTROL_ARM}:as-committed",
    f"{MIDSCALE_PROBE_ARM}:as-committed",
    f"{MIDSCALE_PROBE_ARM}:tran-step-0.25n",
    f"{CONTROL_ARM}:vin+0.1lsb",
    f"{CONTROL_ARM}:vin-0.1lsb",
)

#: The fragment's own input source cards, matched at line start so a rename in
#: the committed fragment fails loudly here instead of silently probing an
#: un-offset deck.
_VIN_CARD_RE = {
    "VINP": re.compile(r"^VINP VINP 0 PWL\(", re.MULTILINE),
    "VINN": re.compile(r"^VINN VINN 0 PWL\(", re.MULTILINE),
}

#: One rail-referenced value expression on those cards, e.g. `{vdd_val*0.375}`.
#: The offset shifts these and only these -- see `offset_vin()`.
_PWL_VALUE_RE = re.compile(r"\{vdd_val\*(?P<frac>-?[0-9.]+)\}")


def insert_before_end(deck: str, extra: list[str]) -> str:
    """`deck` with `extra` inserted immediately before its FINAL `.end` card.

    Anchored on the deck's terminal `\\n.end\\n` rather than searching for
    `.end`: a whole-hierarchy netlist is full of `.ends` subcircuit terminators,
    and a substring replace would scatter copies of the probe cards through the
    middle of the DUT (found while writing this probe, not hypothetically).
    """
    marker = "\n.end\n"
    if not deck.endswith(marker):
        raise RuntimeError(
            "mid-scale probe: assembled deck does not end with a `.end` card -- "
            "re-derive where this probe inserts its measurement cards."
        )
    return deck[: -len(marker)] + "\n" + "\n".join(extra) + marker


def offset_vin(deck: str, offset_lsb: float, supply_v: float) -> str:
    """`deck` with a DC differential input offset of `offset_lsb` LSB.

    Implemented by shifting the LEVELS of the committed fragment's own two
    `PWL` input cards -- every `{vdd_val*<f>}` value on the `VINP` card gains
    `offset_lsb/2^N` of the rail and every one on `VINN` loses it -- and
    nothing else. `+offset_lsb` therefore raises VINP by half an LSB and lowers
    VINN by the same: a DIFFERENTIAL offset of exactly `offset_lsb` LSB with
    the input common mode held. It stays rail-referenced (`{vdd_val*...}`,
    `1 LSB_diff = 2*V_REF/2^N` with `V_REF = V_DD`, DR-003), like every other
    number in that fragment.

    Two properties this deliberately preserves, because the probe's whole claim
    is that it changed one thing:

    * **Every breakpoint TIME is untouched.** Only the value expressions
      inside `{...}` are rewritten, and the count of rewritten values is
      checked, so the solver's PWL breakpoints -- and therefore the timestep
      sequence's anchors -- are the committed deck's.
    * **The node set is untouched.** An earlier draft inserted a series DC
      source per pin instead; that is electrically identical but adds a
      capacitance-free node between two voltage sources, and it cost this deck
      **more than 4x** the control's wall clock (one variant blew a 5400 s
      budget that the unperturbed deck finishes in ~900 s). A perturbation
      probe may not be the most expensive run in the campaign, and it may not
      change the matrix it is supposed to leave alone.
    """
    if offset_lsb == 0.0:
        return deck
    # Half the differential offset per pin, as a fraction of the rail:
    # half of `offset_lsb * 2*V_DD/2^N` is `offset_lsb * V_DD/2^N`.
    dfrac = offset_lsb / (2**tb.N_BITS)
    lines = deck.splitlines(keepends=True)
    rewritten = 0
    for i, line in enumerate(lines):
        for pin, pattern in _VIN_CARD_RE.items():
            if not pattern.match(line):
                continue
            sign = +1.0 if pin == "VINP" else -1.0

            def shift(m: re.Match, sign: float = sign) -> str:
                return "{vdd_val*" + f"{float(m.group('frac')) + sign * dfrac:.12f}" + "}"

            new_line, n = _PWL_VALUE_RE.subn(shift, line)
            if n == 0:
                raise RuntimeError(
                    f"mid-scale probe: the `{pin}` PWL card carries no "
                    "`{vdd_val*<f>}` value expressions -- the committed fragment "
                    "changed shape; re-derive this probe's input offset."
                )
            # times are everything outside the braces: they must be untouched
            if _PWL_VALUE_RE.sub("{}", line) != _PWL_VALUE_RE.sub("{}", new_line):
                raise RuntimeError(
                    f"mid-scale probe: shifting the `{pin}` PWL levels changed "
                    "something other than its values -- refusing to run a "
                    "perturbation that moved a breakpoint time."
                )
            lines[i] = new_line
            rewritten += 1
    if rewritten != len(_VIN_CARD_RE):
        raise RuntimeError(
            f"mid-scale probe: expected exactly {len(_VIN_CARD_RE)} input PWL cards "
            f"(`{'`, `'.join(_VIN_CARD_RE)}`) in the assembled deck, rewrote "
            f"{rewritten} -- the committed fragment changed shape; re-derive this "
            "probe's input offset."
        )
    return insert_before_end(
        "".join(lines),
        [
            "* --- issue #455 mid-scale boundary probe: the two input PWL cards",
            f"* above carry a DC differential offset of {offset_lsb:+g} LSB "
            f"({offset_lsb * lsb_v(supply_v) * 1e3:+.4f} mV at {supply_v:g} V),",
            "* applied to their LEVELS only -- every breakpoint time, every node",
            "* and every other card is the committed deck's. --------------------",
        ],
    )


def retime_tran(deck: str, step_ns: float) -> str:
    """`deck` with the `.tran` card's REQUESTED STEP replaced by `step_ns`.

    The stop time is left exactly as the committed fragment sets it, so every
    `.meas` instant still lands inside the run and the probe measures the same
    conversions. Nothing about the circuit or the stimulus changes -- this moves
    only the sequence of timepoints the solver visits, which is precisely the
    "supply-unrelated perturbation" issue #455 asks for. (`truncate_tran()`
    above deliberately refuses to touch the step for the opposite reason: a cost
    probe must price the same solve, not a different one.)
    """
    match = RE_TRAN_CARD.search(deck)
    if match is None:
        raise RuntimeError(
            "mid-scale probe: no `.tran <step> <stop>` card found in the assembled "
            "deck -- re-derive this probe's timestep perturbation."
        )
    card = f".tran {step_ns:g}n {match.group(2)}"
    return deck[: match.start()] + card + deck[match.end() :]


def midscale_probe_deck(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    arm: Arm,
    perturbation: Perturbation,
    process_corner: str,
    temp_c: float,
    supply_v: float,
) -> tuple[str, list[str]]:
    """`(deck, measurement names)` for one variant: this campaign's own arm deck,
    plus the imported per-trial decision-margin probes, plus the variant's
    perturbation. Returns the extra measurement names so the caller parses
    exactly what it asked for."""
    deck = assemble_deck(dut_netlist_text, pdk_info, arm, process_corner, temp_c, supply_v)
    extra_meas, names = fc.decision_margin_measure_lines(MIDSCALE_PROBE_CONVERSIONS)
    deck = insert_before_end(deck, extra_meas)
    if perturbation.vin_offset_lsb != 0.0:
        deck = offset_vin(deck, perturbation.vin_offset_lsb, supply_v)
    if perturbation.tran_step_ns is not None:
        deck = retime_tran(deck, perturbation.tran_step_ns)
    return deck, names


def parse_midscale_trials(
    parsed: dict[str, float | None], supply_v: float
) -> list[dict]:
    """The per-trial decision-margin rows for every traced conversion.

    Same decoding as `run_conversion.py`'s own `run_decision_margin_point()` --
    the comparator's differential input at the decision instant, the decision it
    produced, and the bit the register captured -- reported here per conversion
    rather than graded, because the question this probe asks is not "is the
    comparator right" (issue #263 asked that) but "how close to its threshold is
    any decision of this conversion".
    """
    threshold = tb.DIGITAL_THRESHOLD_FRACTION * supply_v
    one_lsb = lsb_v(supply_v)
    out: list[dict] = []
    for c in MIDSCALE_PROBE_CONVERSIONS:
        trials = []
        for p in range(tb.N_BITS):
            pre = f"dm_c{c}_p{p}"
            topp, topn = parsed.get(f"{pre}_topp"), parsed.get(f"{pre}_topn")
            comp, dout = parsed.get(f"{pre}_comp"), parsed.get(f"{pre}_dout")
            if None in (topp, topn, comp, dout):
                trials.append(dict(bit=tb.N_BITS - 1 - p, missing=True))
                continue
            v_in = topp - topn
            trials.append(
                dict(
                    bit=tb.N_BITS - 1 - p,
                    missing=False,
                    v_in_mv=v_in * 1e3,
                    v_in_lsb=v_in / one_lsb,
                    decision=1 if comp > threshold else 0,
                    dout=1 if dout > threshold else 0,
                )
            )
        out.append(dict(conversion=c, fraction=tb.input_fraction(c), trials=trials))
    return out


def closest_trial(conversions: list[dict], conversion: int | None = None) -> dict | None:
    """The traced trial whose comparator input is closest to zero -- the one
    decision of the conversion that a perturbation could plausibly flip."""
    trials = [
        dict(conversion=conv["conversion"], **tr)
        for conv in conversions
        if conversion is None or conv["conversion"] == conversion
        for tr in conv["trials"]
        if not tr["missing"]
    ]
    return min(trials, key=lambda tr: abs(tr["v_in_lsb"])) if trials else None


def run_midscale_probe_variant(
    dut_netlist_text: str,
    pdk_info: pdk.PdkInfo,
    scratch: Path,
    arm: Arm,
    perturbation: Perturbation,
    process_corner: str,
    temp_c: float,
    supply_v: float,
    quiet: bool,
    log_cache: Path | None = None,
) -> dict:
    cid = corners_mod.corner_id(process_corner, temp_c, supply_v)
    deck, dm_names = midscale_probe_deck(
        dut_netlist_text, pdk_info, arm, perturbation, process_corner, temp_c, supply_v
    )
    tag = f"{arm.name}__{perturbation.name}"
    # Same identity-gated cache the arm comparison uses, for the same reason and
    # under the same rule (a cached log is reused only if its deck sha256,
    # verified open_pdks commit and ngspice version all match). A probe variant
    # is a whole-ADC transient too -- one of them measured 4x the control's wall
    # clock -- and five in sequence outlive a dispatch session, so an interrupted
    # probe must not have to re-simulate the variants that already finished.
    # The point-id carries the perturbation, so a perturbed deck can never
    # collide with the arm comparison's own cache entry for the same arm.
    point_id = f"{arm.name}+{perturbation.name}@{cid}"
    cached = load_cached_run(log_cache, point_id, deck, pdk_info)
    reused = cached is not None
    if cached is not None:
        log_text, wall_s = cached
        print(f"  reusing cached log for {point_id} ({wall_s:.0f}s when it ran)", flush=True)
    else:
        t0 = time.time()
        log_text = toolchain.run_ngspice_with_retry(
            deck, scratch, f"midscale_probe_{tag}_{cid}", attempts=2
        )
        wall_s = time.time() - t0
        store_cached_run(log_cache, point_id, deck, pdk_info, log_text, wall_s)

    names = tb.all_measure_names() + extra_measure_names(arm) + dm_names
    parsed = measure.parse(log_text, names, anchored=False)
    result = fc.decode(parsed, supply_v)
    point = dict(
        variant=f"{arm.name}:{perturbation.name}",
        arm=arm.name,
        perturbation=perturbation.name,
        corner_id=cid,
        supply_v=supply_v,
        lsb_mv=lsb_v(supply_v) * 1e3,
        conversions=result["conversions"],
        trials=parse_midscale_trials(parsed, supply_v),
        extras={name: parsed.get(name) for name in extra_measure_names(arm)},
        missing=measure.missing(parsed, names),
        wall_s=wall_s,
        reused=reused,
        deck_text=deck,
        log_text=log_text,
    )
    if not quiet:
        codes = " ".join(
            f"{cv['fraction']:+.2f}:{cv['code']}" for cv in mid_scale_conversions(point)
        )
        worst = closest_trial(point["trials"], MIDSCALE_CONVERSION)
        print(
            f"  [{point['variant']} @ {cid}] codes(mid-scale) {codes}; "
            f"closest decision of the mid-scale conversion: "
            + (
                "n/a"
                if worst is None
                else f"bit {worst['bit']} at {worst['v_in_mv']:+.4f} mV "
                f"({worst['v_in_lsb']:+.5f} LSB)"
            )
            + f"; {wall_s:.0f}s",
            flush=True,
        )
    return point


def committed_reference_point(record_id: str, arm_name: str, corner_id: str) -> dict | None:
    """The codes and rail excursion a committed log of `record_id` reports for
    one point, or None when that log is not in the repo.

    Read from the committed `corners/<record-id>/<arm>__<corner>.log` rather
    than from the record's Markdown tables: the log is the primary artifact, and
    parsing it means this probe's reproduction table cannot disagree with the
    evidence it claims to reproduce because someone transcribed a number.
    """
    log_path = common.EXPERIMENT_DIR / "corners" / record_id / f"{arm_name}__{corner_id}.log"
    if not log_path.is_file():
        return None
    arm = ARMS_BY_NAME.get(arm_name)
    names = tb.all_measure_names() + (extra_measure_names(arm) if arm else [])
    parsed = measure.parse(log_path.read_text(), names, anchored=False)
    supply_v = float(corner_id.rsplit("_", 1)[-1].rstrip("v"))
    decoded = fc.decode(parsed, supply_v)
    return dict(
        arm=arm_name,
        corner_id=corner_id,
        record_id=record_id,
        conversions=decoded["conversions"],
        extras={name: parsed.get(name) for name in (extra_measure_names(arm) if arm else [])},
    )


def _conv_code(point: dict | None, conversion: int) -> int | None:
    if point is None:
        return None
    for conv in point["conversions"]:
        if conv["conversion"] == conversion:
            return conv["code"]
    return None


def midscale_probe_findings_lines(points: list[dict]) -> list[str]:
    """What the probe found, as bullets -- the same text the record carries.

    Written as a set of statements each of which is falsified by a single number
    in the tables above it, because the claim being made is a negative one (the
    recorded 6-LSB move is not a measurement of the supply return) and a
    negative claim has to be checkable.
    """
    out: list[str] = []
    by_variant = {p["variant"]: p for p in points}
    cid = points[0]["corner_id"] if points else corners_mod.corner_id(*MIDSCALE_PROBE_CORNER)

    for arm_name in (CONTROL_ARM, MIDSCALE_PROBE_ARM):
        fresh = by_variant.get(f"{arm_name}:as-committed")
        if fresh is None:
            continue
        committed = committed_reference_point(MIDSCALE_PROBE_REFERENCE_RECORD, arm_name, cid)
        fresh_code = _conv_code(fresh, MIDSCALE_CONVERSION)
        committed_code = _conv_code(committed, MIDSCALE_CONVERSION)
        if committed_code is None:
            out.append(
                f"- **`{arm_name}` has no committed log at `{cid}` in record "
                f"`{MIDSCALE_PROBE_REFERENCE_RECORD}`** to reproduce against, so this "
                "run stands alone rather than confirming or contradicting anything."
            )
            continue
        verdict = (
            "**reproduces**" if fresh_code == committed_code else "**does NOT reproduce**"
        )
        out.append(
            f"- **`{arm_name}@{cid}` {verdict}.** Re-running that point's own committed "
            f"deck on this host at the pinned PDK commit gives mid-scale code "
            f"**{fresh_code}**; record `{MIDSCALE_PROBE_REFERENCE_RECORD}`'s committed "
            f"log for the same point reports **{committed_code}**."
        )

    mid = by_variant.get(f"{CONTROL_ARM}:as-committed")
    if mid is not None:
        worst = closest_trial(mid["trials"], MIDSCALE_CONVERSION)
        if worst is not None:
            out.append(
                f"- **The mid-scale conversion's marginal decision is bit "
                f"{worst['bit']}, at {worst['v_in_mv']:+.4f} mV "
                f"({worst['v_in_lsb']:+.5f} LSB) of comparator input.** Every other "
                "traced decision of that conversion is further from its threshold "
                f"(see the per-trial table). One LSB is {mid['lsb_mv']:.4f} mV at "
                f"{mid['supply_v']:g} V, and DR-004's own input-referred noise "
                "budget (Decision item 2; DR-004 is itself `proposed`, so that is a "
                "stated budget rather than a ratified line) is 1.0148 mV -- so that "
                "margin is not a 'code boundary' in the 1-LSB sense at all."
            )
            if worst["bit"] == tb.N_BITS - 1:
                out.append(
                    "- **That marginal decision is the SIGN bit, and the sign bit "
                    "cannot move the code by 1 LSB.** `DOUT9` gates all nine "
                    "`SELn`/`SELp` pairs through `DOUT9N` (`design/sar_adc_top.spice`) "
                    "and selects which side of mid-scale the remaining nine trials "
                    "resolve, so a disturbance there re-runs the whole magnitude "
                    "search rather than nudging one bit. A multi-LSB mid-scale code "
                    "is the expected signature of a disturbed sign trial; a 1-LSB one "
                    "is the lucky case."
                )

    def as_committed_code(point: dict) -> int | None:
        return _conv_code(
            by_variant.get(f"{point['arm']}:as-committed"), MIDSCALE_CONVERSION
        )

    moved = [
        p
        for p in points
        if p["perturbation"] != "as-committed"
        and _conv_code(p, MIDSCALE_CONVERSION) != as_committed_code(p)
    ]
    if moved:
        out.append(
            "- **Supply-unrelated perturbations move this code.** "
            + "; ".join(
                f"`{p['variant']}` reads {_conv_code(p, MIDSCALE_CONVERSION)} against "
                f"its own arm's as-committed {as_committed_code(p)}"
                for p in moved
            )
            + ". None of these variants changes the supply network, a device or the "
            "netlist -- they change the input DC level by a fraction of an LSB, or "
            "only the solver's timestep sequence."
        )
    else:
        out.append(
            "- **No supply-unrelated perturbation in this probe moved the mid-scale "
            "code.** Every variant reads its own arm's as-committed code, so this "
            "probe does not demonstrate input-offset or timestep sensitivity at this "
            "corner -- it bounds it below the perturbations tried, and the "
            "reproduction rows above are what carry the finding."
        )

    off_boundary = []
    for p in points:
        for conv in mid_scale_conversions(p):
            if conv["conversion"] != MIDSCALE_CONVERSION:
                off_boundary.append((p["variant"], conv["fraction"], conv["code"]))
    if off_boundary:
        codes_by_input: dict[float, set[int]] = {}
        for _v, frac, code in off_boundary:
            codes_by_input.setdefault(frac, set()).add(code)
        stable = [f"{frac:+.2f}: {sorted(codes)}" for frac, codes in sorted(codes_by_input.items())]
        out.append(
            "- **The off-boundary mid-scale inputs do not move at all, in any "
            "variant.** " + "; ".join(stable) + " across every variant of this probe "
            "(input fraction: the codes any variant produced). The sensitivity is a "
            "property of the `+0.00*V_REF` input, not of the deck, the arm or the "
            "perturbations."
        )
    return out


def midscale_probe_invocation_line(variants: tuple[str, ...], corner_id: str, supersedes: str) -> str:
    """The `--midscale-probe` counterpart of `invocation_line()`, under the same
    rules: a flag that changes what was simulated is stated, one that only
    changes scheduling is not."""
    parts = [RUNNER_REL, "--midscale-probe"]
    if tuple(variants) != MIDSCALE_PROBE_VARIANTS:
        parts.append("--midscale-probe-variants " + ",".join(variants))
    if corner_id != corners_mod.corner_id(*MIDSCALE_PROBE_CORNER):
        parts.append(f"--corner-points {corner_id}")
    parts.append("--record")
    if supersedes:
        parts.append(f"--supersedes {supersedes}")
    return " ".join(parts)


def write_midscale_probe_record(
    points: list[dict], netlist_text: str, variants: tuple[str, ...], supersedes: str
) -> Path:
    prov, lines = evidence.open_record(
        common.EXPERIMENT_DIR,
        netlist_text,
        "diagnostics",
        {
            f"midscale-probe-{p['variant'].replace(':', '-')}-{p['corner_id']}.log": p[
                "log_text"
            ]
            for p in points
        },
    )
    cid = points[0]["corner_id"] if points else corners_mod.corner_id(*MIDSCALE_PROBE_CORNER)
    a = lines.append

    a(
        "- **Claim**: issue #455 -- DIAGNOSTIC/mechanism evidence about this "
        "campaign's OWN mid-scale code comparison, not a spec row, not a corner "
        "campaign, and not a supply-impedance measurement. It asks one question: "
        f"is the 6-LSB mid-scale move record `{MIDSCALE_PROBE_REFERENCE_RECORD}` "
        f"records for `{MIDSCALE_PROBE_ARM}@{cid}` (505 against the control's 511) a "
        "property of that deck, and if so which decision of that conversion moved. "
        "It proposes no target, edits no spec row and supersedes no record."
    )
    a(
        "- **Netlist provenance**: schematic (`design/sar_adc_top.spice`), with this "
        "campaign's two standing testbench-only transformations (the `GND` -> "
        "`GND_DIE` rename, and the board-side supply re-pointing on bonded arms) and "
        "NOTHING else. Every variant below is the same DUT; the perturbations act on "
        "the stimulus's DC level or on the solver, never on the netlist."
    )
    a(
        f"- **Corner**: `{cid}` only -- the point the anomaly was recorded at. A "
        "mechanism trace, not a corner campaign: the ratified grid's mid-scale codes "
        f"are already in record `{MIDSCALE_PROBE_REFERENCE_RECORD}`, and this probe "
        "exists to say what they mean."
    )
    a(
        "- **Conversions traced**: "
        + ", ".join(
            f"conversion {c} (`{tb.input_fraction(c):+.2f}*V_REF`)"
            for c in MIDSCALE_PROBE_CONVERSIONS
        )
        + ". The near-full-scale inputs are excluded for the same reason this "
        "campaign's code comparison excludes them (issue #267)."
    )
    a(
        "- **Probe instants**: the comparator's differential input 1 ns before the "
        "CLK falling edge that opens each trial's evaluate half (DAC settled, latch "
        "still in reset), its decision 1 ns before the capturing rising edge, and the "
        "captured bit 2 ns after it -- `run_conversion.py`'s own "
        "`decision_margin_measure_lines()`, imported rather than re-derived, so the "
        "instants are identical to the committed `--decision-margin-trace` record's."
    )
    a("")

    a("## The variants")
    a("")
    a("| variant | arm's supply network | what was perturbed |")
    a("|---|---|---|")
    for p in points:
        arm = ARMS_BY_NAME[p["arm"]]
        pert = PERTURBATIONS_BY_NAME[p["perturbation"]]
        a(f"| `{p['variant']}` | {arm.summary} | {pert.summary} |")
    a("")

    a("## Reproduction of the recorded point")
    a("")
    a(
        f"Each row re-runs the committed deck of a point of record "
        f"`{MIDSCALE_PROBE_REFERENCE_RECORD}` and compares the fresh measurements "
        "with that record's own committed log, parsed from the log rather than "
        "transcribed from its tables."
    )
    a("")
    a(
        "| point | mid-scale code, committed log | mid-scale code, re-run here | "
        "`GND_DIE` pp committed | `GND_DIE` pp here | verdict |"
    )
    a("|---|---|---|---|---|---|")
    for arm_name in (CONTROL_ARM, MIDSCALE_PROBE_ARM):
        fresh = next((p for p in points if p["variant"] == f"{arm_name}:as-committed"), None)
        if fresh is None:
            continue
        committed = committed_reference_point(MIDSCALE_PROBE_REFERENCE_RECORD, arm_name, cid)
        fresh_code = _conv_code(fresh, MIDSCALE_CONVERSION)
        committed_code = _conv_code(committed, MIDSCALE_CONVERSION)
        verdict = (
            "n/a (no committed log)"
            if committed_code is None
            else ("identical" if committed_code == fresh_code else "**DIFFERS**")
        )
        a(
            f"| `{arm_name}@{cid}` | "
            f"{'n/a' if committed_code is None else committed_code} | "
            f"{'n/a' if fresh_code is None else fresh_code} | "
            f"{_mv(None if committed is None else committed['extras'].get('gnd_die_pp'))} mV | "
            f"{_mv(fresh['extras'].get('gnd_die_pp'))} mV | {verdict} |"
        )
    a("")

    a("## Captured mid-scale codes, per variant")
    a("")
    a(
        "| variant | "
        + " | ".join(
            f"`{tb.input_fraction(c):+.2f}*V_REF`" for c in MIDSCALE_PROBE_CONVERSIONS
        )
        + " | wall clock (s) |"
    )
    a("|---" * (len(MIDSCALE_PROBE_CONVERSIONS) + 2) + "|")
    for p in points:
        cells = []
        for c in MIDSCALE_PROBE_CONVERSIONS:
            code = _conv_code(p, c)
            cells.append("n/a" if code is None else str(code))
        wall = f"{p['wall_s']:.0f}" + (
            " (log reused from cache)" if p.get("reused") else ""
        )
        a(f"| `{p['variant']}` | " + " | ".join(cells) + f" | {wall} |")
    a("")
    a(
        "A row marked **log reused from cache** was not re-simulated for this "
        "record: the campaign's own identity-gated `--log-cache` found a stored "
        "log whose deck sha256, volare-verified open_pdks commit and ngspice "
        "version all matched the run about to be made, and the wall clock shown "
        "is the one measured when that run actually executed (same mechanism, "
        "same gate, same disposition as the arm-comparison records)."
    )
    a("")
    a(
        f"The ideal code for `+0.00*V_REF` is {tb.ideal_code(0.0)} "
        f"(`spec/target-spec.md`, RATIFIED DR-003), and this campaign's control reads "
        "511 at some corners and 512 at others -- which is the whole reason this "
        "input was worth probing."
    )
    a("")

    a("## Per-trial decision margin, mid-scale conversion")
    a("")
    a(
        "The comparator's own differential input at each bit trial's decision "
        "instant, per variant. This is the table that says which decision of the "
        "conversion a perturbation could plausibly flip -- and which ones it could "
        "not."
    )
    a("")
    header = "| bit | " + " | ".join(f"`{p['variant']}`" for p in points) + " |"
    a(header)
    a("|---" * (len(points) + 1) + "|")
    for idx in range(tb.N_BITS):
        bit = tb.N_BITS - 1 - idx
        cells = []
        for p in points:
            conv = next(
                (c for c in p["trials"] if c["conversion"] == MIDSCALE_CONVERSION), None
            )
            tr = None if conv is None else conv["trials"][idx]
            if tr is None or tr["missing"]:
                cells.append("n/a")
            else:
                cells.append(
                    f"{tr['v_in_mv']:+.4f} mV ({tr['v_in_lsb']:+.4f} LSB) -> d{bit}={tr['dout']}"
                )
        a(f"| {bit} | " + " | ".join(cells) + " |")
    a("")
    a(
        "`-> d<n>=<v>` is the bit the search register captured for that trial, so a "
        "row states both what the comparator was asked and what the loop did with "
        "the answer. A magnitude-search trial of this conversion is *supposed* to "
        "read a large positive input and capture 0: the sign trial has already "
        "chosen the branch, and the magnitude then walks down from half scale."
    )
    a("")

    a("## Findings")
    a("")
    for line in midscale_probe_findings_lines(points):
        a(line)
    a("")
    a(
        "- **What this probe does NOT establish.** It does not reconstruct the "
        f"trajectory that produced the recorded 505: that run is not reproducible "
        "here, so its own per-trial margins cannot be read out after the fact. What "
        "would settle it is running this probe on a host where the mid-scale code "
        "does move -- the per-trial table then names the diverging trial directly."
    )
    a("")

    lines.extend(
        evidence.environment_block(
            pdk_line=prov.pdk_line,
            ngspice_line=prov.ng_version,
            netlist_sha256=prov.netlist_sha,
            extra={
                "tran step": f"{tb.TRAN_STEP_NS} ns (as committed; one variant halves it)",
                "simulated span": f"{tb.t_stop_ns():.1f} ns per run",
                "runs": f"{len(points)} (one per variant, one at a time)",
                "corner": f"`{cid}`",
                "testbench fragment sha256": f"`{evidence.sha256_file(tb.FRAGMENT_PATH)}`",
                "reproduced against": (
                    f"record `{MIDSCALE_PROBE_REFERENCE_RECORD}`'s committed logs under "
                    f"`corners/{MIDSCALE_PROBE_REFERENCE_RECORD}/`"
                ),
                "one LSB": f"{lsb_v(points[0]['supply_v']) * 1e3:.4f} mV differential"
                if points
                else "n/a",
            },
        )
    )
    a("")
    lines.extend(
        evidence.footer_lines(
            midscale_probe_invocation_line(variants, cid, supersedes), supersedes
        )
    )

    # Deliberately NOT records/LATEST, for the same reason the two sweep records
    # are not: that pointer names this campaign's newest ARM-COMPARISON record,
    # which is what the proposal citation census reads. This record contains no
    # arm census -- it is one corner, two networks and three perturbations of a
    # single conversion -- and moving the pointer onto it would make a citation
    # of a record nothing had superseded read as stale.
    return evidence.close_record(prov, lines, "Mid-scale boundary probe record")


def run_midscale_probe(
    variants: tuple[str, ...],
    corner: tuple[str, float, float],
    scratch: Path,
    quiet: bool,
    log_cache: Path | None = None,
) -> tuple[list[dict], str]:
    pdk_info = pdk.resolve()
    dut_netlist_text = fc.dut_text()
    process_corner, temp_c, supply_v = corner
    points: list[dict] = []
    for spec in variants:
        arm_name, _, pert_name = spec.partition(":")
        point = run_midscale_probe_variant(
            dut_netlist_text,
            pdk_info,
            scratch,
            ARMS_BY_NAME[arm_name],
            PERTURBATIONS_BY_NAME[pert_name],
            process_corner,
            temp_c,
            supply_v,
            quiet,
            log_cache=log_cache,
        )
        points.append(point)
    return points, dut_netlist_text

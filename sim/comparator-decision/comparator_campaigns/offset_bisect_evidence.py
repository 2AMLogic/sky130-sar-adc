"""offset bisect evidence campaign for the comparator-decision driver (issue #613 split of run.py)."""
from __future__ import annotations

from pathlib import Path

from .common import (
    DUT_FRAGMENT,
    DUT_FRAGMENT_EXTRACTED,
    EXPERIMENT_DIR,
    PICKOFF_NS,
    RESET_NS,
    VDD,
    _dut_lines,
    _dut_provenance,
)
from .offset_bisect import (
    BISECT_EVALUATE_NS,
    BISECT_MAX_MV,
    BISECT_SCAN_MV,
    BISECT_SCHEMATIC_BAND_BOUND_MV,
    BISECT_SCHEMATIC_OFFSET_BOUND_MV,
    BISECT_SCHEMATIC_RECORD_ID,
    BISECT_TOL_MV,
    BisectCornerResult,
)
from .regen import (
    _finalize_record,
)
from .regen_corners import (
    DIFFERENTIAL_LSB_MV,
)
from harness import corners as corners_mod, evidence, toolchain

def _bisect_edge_cell(edge_mv: float | None, unc_mv: float | None) -> str:
    if edge_mv is None:
        return "n/a"
    return f"{edge_mv:+.4f} +-{unc_mv:.4f}"


def _postlayout_half_lsb_verdict(
    results: list[BisectCornerResult], half_lsb_mv: float,
) -> tuple[str, list[str]]:
    """DR-020's supersession test for an extracted-DUT run (issue #525).

    Returns (verdict, reasons) where verdict is one of:

    * ``"TRIGGERED"`` -- some corner point has a RESOLVED systematic offset
      with |offset| >= half-LSB, or a RESOLVED dead band >= half-LSB. DR-020
      Decision 1-2 must then be superseded by a NEW decision record.
    * ``"UNDETERMINED"`` -- nothing is triggered, but at least one point
      either yielded no boundary pair or has a bracket whose upper bound
      reaches half-LSB, so half-LSB scale cannot be excluded.
    * ``"NOT-TRIGGERED"`` -- every point is bounded and both quantities'
      upper bounds (value + bracket uncertainty) are below half-LSB: DR-020 is
      corroborated at this netlist class.

    Kept a pure function of `results` so the record's verdict sentence and
    the tests turn on the same rule.
    """
    triggered: list[str] = []
    undetermined: list[str] = []
    for r in results:
        if not r.bounded:
            undetermined.append(
                f"`{r.corner_id}` yielded no boundary pair (status {r.status})"
            )
            continue
        off_hi = abs(r.offset_mv) + r.offset_unc_mv
        band_hi = r.dead_band_mv + r.dead_band_unc_mv
        if r.offset_resolved and abs(r.offset_mv) >= half_lsb_mv:
            triggered.append(
                f"`{r.corner_id}` systematic offset {r.offset_mv:+.4f} "
                f"+-{r.offset_unc_mv:.4f} mV"
            )
        elif off_hi >= half_lsb_mv:
            undetermined.append(
                f"`{r.corner_id}` offset upper bound {off_hi:.4f} mV reaches "
                "half-LSB"
            )
        if r.dead_band_resolved and r.dead_band_mv >= half_lsb_mv:
            triggered.append(
                f"`{r.corner_id}` dead band {r.dead_band_mv:.4f} "
                f"+-{r.dead_band_unc_mv:.4f} mV"
            )
        elif band_hi >= half_lsb_mv:
            undetermined.append(
                f"`{r.corner_id}` band upper bound {band_hi:.4f} mV reaches "
                "half-LSB"
            )
    if triggered:
        return "TRIGGERED", triggered
    if undetermined:
        return "UNDETERMINED", undetermined
    return "NOT-TRIGGERED", []


def _signed_delay_asymmetry(r: BisectCornerResult) -> list[tuple[float, float]]:
    """[(|V| mV, t(+V) - t(-V) ns)] over every |Vindiff| probed on both signs
    with a decision delay, ascending in |V|."""
    by_v = {
        round(p.vindiff_mv, 6): p.decide_time_ns for p in r.probes
        if p.decide_time_ns is not None
    }
    return sorted(
        (v, by_v[v] - by_v[round(-v, 6)])
        for v in by_v
        if v > 0 and round(-v, 6) in by_v
    )


def _delay_asymmetry_agrees_with_offset(r: BisectCornerResult) -> bool | None:
    """Item 4's falsifiability check for a DUT that is NOT symmetric by
    construction (issue #525). A systematic offset Vos shifts the effective
    overdrive to V - Vos, so a positive Vos makes every `+V` decision slower
    than its `-V` mirror (t(+V) - t(-V) > 0) and a negative one the reverse.
    Returns None when there is nothing to check (offset not resolved, or no
    matched pair); otherwise whether EVERY matched pair's sign agrees."""
    pairs = _signed_delay_asymmetry(r)
    if not r.bounded or not r.offset_resolved or not pairs:
        return None
    want_pos = r.offset_mv > 0
    return all(d != 0.0 and (d > 0) == want_pos for _, d in pairs)


def _offset_bisect_postlayout_delay_check(
    a, results: list[BisectCornerResult],
) -> None:
    """Item 4 for an extracted-DUT record: the symmetric-DUT check (+V and -V
    delays must agree) does not apply to a layout that is not symmetric by
    construction, so the falsifiable prediction becomes the SIGN of the
    delay asymmetry, which the measured offset fixes independently."""
    a(
        "**4. Decision-delay asymmetry, the falsifiability check for an "
        "asymmetric DUT.** The extracted netlist is not symmetric by "
        "construction, so `+V` and `-V` delays need NOT agree. What a real "
        "systematic offset Vos does predict is their ORDER: the effective "
        "overdrive becomes V - Vos, so Vos > 0 makes every `+V` decision "
        "slower than its `-V` mirror (t(+V) - t(-V) > 0) and Vos < 0 the "
        "reverse. That sign is fixed by the boundary bisection, and the "
        "delays are measured independently of it, so a classification sign "
        "error or a spurious offset would not survive it. Measured, per corner "
        "point (matched |Vindiff| pairs where both signs were probed):"
    )
    a("")
    a(
        "| corner-id | matched pairs | t(+V) - t(-V) per pair (ns) | "
        "sign agrees with measured offset? |"
    )
    a("|---|---|---|---|")
    for r in results:
        pairs = _signed_delay_asymmetry(r)
        cells = ", ".join(f"{v:g} mV: {d:+.4f}" for v, d in pairs) or "n/a"
        agrees = _delay_asymmetry_agrees_with_offset(r)
        verdict = (
            "n/a (offset not resolved)" if agrees is None
            else ("**yes**, every pair" if agrees else "**NO**")
        )
        a(f"| `{r.corner_id}` | {len(pairs)} | {cells} | {verdict} |")
    a("")


def _offset_bisect_postlayout_comparison(
    a, results: list[BisectCornerResult], half_lsb_mv: float,
) -> None:
    """The 'Post-layout vs schematic' section of an extracted-DUT record:
    side-by-side against `BISECT_SCHEMATIC_RECORD_ID`, plus DR-020's
    half-LSB supersession verdict, stated explicitly either way."""
    a("## Post-layout vs schematic (issue #525)")
    a("")
    a(
        "Comparison point: `sim/comparator-decision/records/"
        f"{BISECT_SCHEMATIC_RECORD_ID}.md` -- the same `offset-bisect` "
        "stimulus, search, bisection floor, and PVT points on the "
        "schematic-derived netlist, which bounded both quantities at both "
        f"points: |offset| < {BISECT_SCHEMATIC_OFFSET_BOUND_MV} mV and band < "
        f"{BISECT_SCHEMATIC_BAND_BOUND_MV} mV, neither resolved. Half-LSB "
        f"(DR-003 Item 3) = {half_lsb_mv:.4f} mV."
    )
    a("")
    a(
        "| corner-id | schematic offset (mV) | post-layout offset (mV) | "
        "offset resolved? | schematic band (mV) | post-layout band (mV) | "
        "band resolved? | post-layout upper bound / half-LSB (offset, band) |"
    )
    a("|---|---|---|---|---|---|---|---|")
    for r in results:
        if r.bounded:
            off = f"{r.offset_mv:+.4f} +-{r.offset_unc_mv:.4f}"
            band = f"{r.dead_band_mv:.4f} +-{r.dead_band_unc_mv:.4f}"
            off_res = "**yes**" if r.offset_resolved else "no"
            band_res = "**yes**" if r.dead_band_resolved else "no"
            ratio = (
                f"{(abs(r.offset_mv) + r.offset_unc_mv) / half_lsb_mv:.3f}, "
                f"{(r.dead_band_mv + r.dead_band_unc_mv) / half_lsb_mv:.3f}"
            )
        else:
            off = band = off_res = band_res = ratio = f"n/a ({r.status})"
        a(
            f"| `{r.corner_id}` | < {BISECT_SCHEMATIC_OFFSET_BOUND_MV} | {off} "
            f"| {off_res} | < {BISECT_SCHEMATIC_BAND_BOUND_MV} | {band} | "
            f"{band_res} | {ratio} |"
        )
    a("")
    appeared = [
        r for r in results
        if r.bounded and (r.offset_resolved or r.dead_band_resolved)
    ]
    if appeared:
        a(
            "**Does either shape appear post-layout? YES, at some magnitude**, "
            "at "
            + ", ".join(f"`{r.corner_id}`" for r in appeared)
            + " (resolved above the bisection floor, where the schematic "
            "netlist resolved neither). Whether that magnitude matters is the "
            "half-LSB test below."
        )
    else:
        a(
            "**Does either shape appear post-layout? NO** -- at every bounded "
            "point neither the systematic offset nor the dead band is resolved "
            "above its bisection floor, the same answer the schematic netlist "
            "gave."
        )
    a("")
    verdict, reasons = _postlayout_half_lsb_verdict(results, half_lsb_mv)
    if verdict == "TRIGGERED":
        a(
            f"**DR-020 supersession trigger: MET.** At half-LSB scale (>= "
            f"{half_lsb_mv:.4f} mV): " + "; ".join(reasons) + ". Per DR-020's "
            "own trigger and issue #525, DR-020 Decision 1-2 must be "
            "SUPERSEDED BY A NEW DECISION RECORD (not patched)."
        )
    elif verdict == "UNDETERMINED":
        a(
            "**DR-020 supersession trigger: UNDETERMINED.** Nothing resolved "
            f"at >= {half_lsb_mv:.4f} mV, but half-LSB scale cannot be "
            "excluded: " + "; ".join(reasons) + ". This record neither "
            "supersedes nor corroborates DR-020."
        )
    else:
        a(
            "**DR-020 supersession trigger: NOT MET.** At every point both "
            "the offset's and the band's upper bound (value + bracket "
            f"uncertainty) is below the {half_lsb_mv:.4f} mV half-LSB, so "
            "DR-020's conclusion is CORROBORATED at the post-layout netlist "
            "class this flow provides (quasi-static `klt pex` R/C), not "
            "superseded."
        )
    a("")


def write_offset_bisect_evidence(
    results: list[BisectCornerResult], note: str = "", supersedes: str = "",
    dut_fragment: Path = DUT_FRAGMENT,
) -> Path:
    raw_logs: dict[str, str] = {}
    for r in results:
        for p in r.probes:
            safe = f"{p.vindiff_mv:.6f}mV".replace("-", "neg").replace(".", "p")
            raw_logs[f"{r.corner_id}__vindiff_{safe}.log"] = p.log_text
    prov, lines = evidence.open_record(
        EXPERIMENT_DIR, _dut_lines(dut_fragment), "corners", raw_logs
    )
    record_path = prov.record_path
    a = lines.append

    bounded = [r for r in results if r.bounded]
    corner_ids = [r.corner_id for r in results]
    n_probes = sum(len(r.probes) for r in results)
    # Issue #525: the extracted (post-layout) DUT is NOT symmetric by
    # construction -- routing parasitics need not match between the two
    # halves -- so the prose that leans on "mismatch-free and symmetric"
    # (the negative-control reading of item 1, the netlist-scope caveat of
    # item 5) must branch on which fragment actually ran.
    extracted = dut_fragment == DUT_FRAGMENT_EXTRACTED

    if extracted:
        a(
            "- **Claim**: none numeric -- INFORMATIONAL. `spec/target-spec.md` "
            "carries no offset row and no dead-band/non-decision row, DRAFT or "
            "ratified, so there is nothing here to grade against and nothing "
            "here asserts a pass. This record is the POST-LAYOUT replication "
            f"(issue #525) of `sim/comparator-decision/records/"
            f"{BISECT_SCHEMATIC_RECORD_ID}.md`'s schematic-level `offset-bisect` "
            "campaign -- same stimulus, same search, same two PVT points, on "
            "the comparator sub-block's `klt pex` extracted netlist. It is the "
            "trigger "
            "`spec/decision-records/DR-020-comparator-offset-and-dead-band-spec-rows.md` "
            "names for superseding itself: a systematic offset or a dead band "
            f"at half-LSB scale (>= {DIFFERENTIAL_LSB_MV / 2:.4f} mV) here "
            "would change DR-020 Decision 1-2 and require a NEW decision record; "
            "anything smaller corroborates DR-020 at this netlist class. See "
            "'Post-layout vs schematic' below for which."
        )
    else:
        a(
            "- **Claim**: none numeric -- INFORMATIONAL. `spec/target-spec.md` "
            "carries no offset row and no dead-band/non-decision row, DRAFT or "
            "ratified, so there is nothing here to grade against and nothing here "
            "asserts a pass. This record measures two quantities a sigma-only "
            "offset characterization cannot express -- the **systematic decision "
            "offset** and the **non-decision (dead) band width** -- and exists to "
            "settle the question "
            "`spec/decision-records/DR-004-comparator-topology-and-noise-budget.md` "
            "left open twice: *\"Offset and regeneration-time spec rows -- "
            "spec/target-spec.md has neither today ... a future record should "
            "decide whether either belongs in the table\"* and *\"A precise (not "
            "order-of-magnitude) offset extraction methodology\"*. "
            "`spec/decision-records/DR-020-comparator-offset-and-dead-band-spec-rows.md` "
            "is the decision record that consumes it."
        )
    a(f"- **Netlist provenance**: {_dut_provenance(dut_fragment)}")
    a(
        corners_mod.corner_matrix_summary_line(
            sorted({r.corner for r in results}),
            sorted({r.temp_c for r in results}),
            sorted({r.supply_v for r in results}),
            len(results),
        )
    )
    a(
        "- **Mismatch**: DISABLED. Every probe below runs the plain process "
        "corner (`tt` / `ss`), not a `*_mm` mismatch corner, and applies no "
        "`rndseed`. That is deliberate and is what makes the measured offset "
        "**systematic**: it is the boundary a mismatch-free DUT already has "
        "from topology and corner models alone, before any per-device draw. "
        "The random/mismatch term is the separate quantity "
        "`sim/comparator-decision/records/20260821-071918-433a294.md` measures "
        "(`tt_mm`, N=16) -- see 'Relationship to the pick-off record' below."
    )
    a(
        f"- **Stimulus**: single reset({RESET_NS}ns, CLK=0)->evaluate(CLK=supply) "
        "edge per probe, from `_regen_deck()` unchanged -- the same deck "
        "`regen`/`regen-corners` use, so a boundary here and a decision delay "
        "there are directly comparable. Decision test |v(OUTP)-v(OUTN)| > "
        "0.5*supply with the sign taken AT THE CROSSING (absolute polarity, "
        "never sign-corrected against the input); Vcm = supply/2; evaluate "
        f"window {BISECT_EVALUATE_NS}ns"
    )
    a(
        f"- **Search**: coarse scan {BISECT_SCAN_MV} mV, outward expansion "
        f"capped at +-{BISECT_MAX_MV:g} mV, then two independent bisections to "
        f"a {BISECT_TOL_MV} mV (100 uV) bracket floor -- {n_probes} transient "
        "probes total across the corner points. Every +- figure below is the "
        "half-width of a converged bracket whose BOTH endpoints were actually "
        "simulated; none is interpolated."
    )
    a(
        f"- **Solver budget**: {toolchain.toolchain_timeout_s():g} s per ngspice "
        f"attempt (`{toolchain.TIMEOUT_ENV_VAR}`; the harness default is "
        f"{toolchain.DEFAULT_TOOLCHAIN_TIMEOUT_S} s), 4 attempts per probe. "
        "Recorded because it is the only thing separating a near-boundary "
        "solver crawl from ordinary contention on a shared host, where the "
        "same probe deck has been measured at both ~18 s and >5 min of CPU "
        "with no change to its text. A probe that exhausts all four attempts "
        "is classified `SOLVER-FLOOR` and ends its refinement with the bracket "
        "reported as-is; it is never counted as the circuit failing to decide. "
        + (
            "No probe below hit that limit."
            if not any(
                p.outcome == "SOLVER-FLOOR" for r in results for p in r.probes
            )
            else "Probes that did hit it are shown as `SOLVER-FLOOR` in the "
            "ladders below."
        )
    )
    if note:
        a(f"- **Note**: {note}")
    a(
        f"- **Overall**: {len(bounded)}/{len(results)} corner point(s) yielded a "
        "bounded pair of decision boundaries"
        + (
            ""
            if len(bounded) == len(results)
            else " -- see the per-corner status column and notes for why the "
            "others did not"
        )
    )
    a("")

    a("## Measured boundaries, systematic offset, and dead band")
    a("")
    a(
        "`negative edge` is the largest Vindiff that still resolved to the "
        "NEGATIVE polarity; `positive edge` is the smallest that resolved to "
        "the POSITIVE one. The systematic offset is their midpoint; the "
        "dead-band width is their separation. A band is called RESOLVED only "
        "when it exceeds the uncertainty the two brackets leave -- otherwise "
        f"it is below the {BISECT_TOL_MV} mV bisection floor and is reported as "
        "such rather than as a number the measurement cannot support."
    )
    a("")
    a(
        "| corner-id | status | negative edge (mV) | positive edge (mV) | "
        "systematic offset (mV) | dead band (mV) | band resolved? | "
        "NO-DECISION probes inside band |"
    )
    a("|---|---|---|---|---|---|---|---|")
    for r in results:
        if r.bounded:
            offset_cell = f"{r.offset_mv:+.4f} +-{r.offset_unc_mv:.4f}"
            band_cell = f"{r.dead_band_mv:.4f} +-{r.dead_band_unc_mv:.4f}"
            resolved_cell = (
                "**yes**" if r.dead_band_resolved
                else f"no (< {r.dead_band_unc_mv:.4f} mV floor)"
            )
            in_band = str(len(r.no_decision_probes_in_band))
        else:
            offset_cell = band_cell = resolved_cell = in_band = "n/a"
        a(
            f"| `{r.corner_id}` | {r.status} | "
            f"{_bisect_edge_cell(r.neg_edge_mv, r.neg_edge_unc_mv)} | "
            f"{_bisect_edge_cell(r.pos_edge_mv, r.pos_edge_unc_mv)} | "
            f"{offset_cell} | {band_cell} | {resolved_cell} | {in_band} |"
        )
    a("")
    a(
        f"Reference scales: the differential LSB is {DIFFERENTIAL_LSB_MV:.4f} mV "
        f"(DR-003 Item 3), so half an LSB -- the smallest differential a correct "
        f"bit trial must resolve -- is {DIFFERENTIAL_LSB_MV / 2:.4f} mV, and the "
        f"bisection floor ({BISECT_TOL_MV} mV) is "
        f"{DIFFERENTIAL_LSB_MV / 2 / BISECT_TOL_MV:.0f}x finer than that."
    )
    a("")

    # --- What this means ---------------------------------------------------
    # Every number in this section is DERIVED from `results`, never typed in,
    # so the prose cannot drift from the table above it on a re-run.
    a("## What this means")
    a("")
    half_lsb_mv = DIFFERENTIAL_LSB_MV / 2.0
    if bounded:
        worst_offset = max(abs(r.offset_mv) for r in bounded)
        worst_offset_unc = max(r.offset_unc_mv for r in bounded)
        # "Resolved" has exactly one meaning throughout this record: larger than
        # the uncertainty the converged bracket leaves. NOTHING below may assert
        # a direction ("is zero" / "is nonzero") that this test does not support
        # -- the whole point of the +- columns is that a bracket half-width is a
        # measurement floor, not decoration.
        offset_resolved = [r for r in bounded if r.offset_resolved]
        # The symmetric mismatch-free nominal point is the negative control: it
        # is the one corner where a RESOLVED offset would indict the
        # measurement rather than describe the circuit.
        controls = [r for r in bounded if r.corner == "tt" and r.temp_c == 27.0]
        control_clean = all(not r.offset_resolved for r in controls)
        if not offset_resolved:
            a(
                f"**1. The systematic decision offset is NOT RESOLVED at any "
                f"corner point measured -- i.e. it is indistinguishable from "
                f"zero.** The largest |offset| is {worst_offset:.4f} mV against "
                f"a bracket uncertainty of +-{worst_offset_unc:.4f} mV, so the "
                f"honest statement is a BOUND: |offset| < "
                f"{worst_offset_unc:.4f} mV, which is "
                f"{half_lsb_mv / worst_offset_unc:.0f}x smaller than the "
                f"{half_lsb_mv:.4f} mV half-LSB a bit trial must resolve. "
                + (
                    "On this EXTRACTED DUT that is a measured result, not a "
                    "control: routing parasitics need not be symmetric between "
                    "the two halves, so nothing forced it to come out at ~0. "
                    "The search itself was validated against the symmetric "
                    "schematic netlist's negative control in "
                    f"`{BISECT_SCHEMATIC_RECORD_ID}`."
                    if extracted else
                    "That is the expected answer for a mismatch-free DUT whose "
                    "input pair is symmetric by construction"
                )
                + (
                    ""
                    if extracted else
                    ", and it is what makes the rest of this record credible: "
                    f"the {', '.join('`' + r.corner_id + '`' for r in controls)}"
                    " point is a NEGATIVE CONTROL, and it passed."
                    if controls else
                    ". NOTE: this campaign did not include the `tt`/27 C "
                    "negative-control point, so nothing here independently "
                    "validates the search against a DUT whose answer is known "
                    "by symmetry."
                )
            )
        else:
            a(
                "**1. A systematic decision offset IS RESOLVED** (|offset| "
                "exceeds the bracket uncertainty) at "
                + "; ".join(
                    f"`{r.corner_id}`: {r.offset_mv:+.4f} +-{r.offset_unc_mv:.4f}"
                    f" mV ({abs(r.offset_mv) / half_lsb_mv:.3f} half-LSB)"
                    for r in offset_resolved
                )
                + ". "
                + (
                    "This is an EXTRACTED DUT, which is not symmetric by "
                    "construction (routing parasitics need not match between "
                    "the two halves), so a resolved offset at `tt`/27 C here "
                    "is a candidate circuit property, not an indictment of the "
                    "measurement: the search was validated against the "
                    "symmetric schematic netlist's negative control in "
                    f"`{BISECT_SCHEMATIC_RECORD_ID}` (|offset| < "
                    f"{BISECT_SCHEMATIC_OFFSET_BOUND_MV} mV at both points), "
                    "using the same stimulus and search as this run."
                    if extracted else
                    "The `tt`/27 C negative control is NOT among them, so the "
                    "search still reproduces ~0 on the DUT whose answer is "
                    "known by symmetry and the resolved offsets above are "
                    "corner effects rather than a measurement artifact."
                    if control_clean and controls else
                    "**WARNING: the `tt`/27 C NEGATIVE CONTROL itself shows a "
                    "resolved offset.** A mismatch-free symmetric DUT at the "
                    "nominal corner must come out at ~0, so this indicts the "
                    "MEASUREMENT before it describes the circuit, and no "
                    "number in this record should be consumed as a circuit "
                    "property until that is explained."
                    if controls else
                    "This campaign did not include the `tt`/27 C negative "
                    "control, so nothing here independently validates the "
                    "search against a DUT whose answer is known by symmetry: "
                    "treat the resolved offsets above as unvalidated."
                )
            )
        a("")
        resolved_bands = [r for r in bounded if r.dead_band_resolved]
        worst_band_floor = max(r.dead_band_unc_mv for r in bounded)
        if resolved_bands:
            a(
                "**2. A non-decision (dead) band IS resolved at "
                + ", ".join(f"`{r.corner_id}`" for r in resolved_bands)
                + ".** "
                + "; ".join(
                    f"`{r.corner_id}`: {r.dead_band_mv:.4f} "
                    f"+-{r.dead_band_unc_mv:.4f} mV, corroborated by "
                    f"{len(r.no_decision_probes_in_band)} probe(s) inside it "
                    "that resolved on neither polarity"
                    for r in resolved_bands
                )
                + f". Window-relative, within the {BISECT_EVALUATE_NS} ns "
                "evaluate window stated above."
            )
        else:
            a(
                f"**2. No non-decision (dead) band is resolved at any corner "
                f"point measured.** Every band comes out at or below its own "
                f"bracket uncertainty (worst: +-{worst_band_floor:.4f} mV), so "
                f"the honest statement is a BOUND -- the band is narrower than "
                f"{worst_band_floor:.4f} mV -- not a width. This is issue "
                "#515's named edge case and it is reported as a bound rather "
                "than as a number the bisection cannot support."
            )
        a("")
        # The only genuinely-undecided probes anywhere, named individually: a
        # reader should not have to scan three ladders to find them.
        undecided = [
            (r, p) for r in results for p in r.probes
            if p.outcome == "NO-DECISION"
        ]
        if undecided:
            a(
                f"**3. {len(undecided)} probe(s) in the whole campaign failed to "
                f"resolve within the {BISECT_EVALUATE_NS} ns window**: "
                + "; ".join(
                    f"`{r.corner_id}` at {p.vindiff_mv:+.6f} mV "
                    f"(ended {p.final_diff_v:+.4f} V differential, "
                    f"{p.relative_outcome()})"
                    for r, p in undecided
                )
                + ". "
                + (
                    "Every one of them is the Vindiff = 0 metastability "
                    "control, which has NO correct answer to get right -- an "
                    "ideally symmetric mismatch-free DUT at exactly zero input "
                    "is metastable by construction. A non-decision there is "
                    "therefore not a dead band; it is the control behaving as "
                    "predicted, and it is excluded from the band corroboration "
                    "count above for exactly that reason."
                    if all(p.vindiff_mv == 0.0 for _, p in undecided)
                    else "At least one is at a NONZERO Vindiff, which is a "
                    "genuine non-decision at a real overdrive -- see the "
                    "ladders."
                )
            )
        else:
            a(
                f"**3. Every probe in the campaign resolved within the "
                f"{BISECT_EVALUATE_NS} ns window**, including the Vindiff = 0 "
                "metastability control (which has no correct answer to get "
                "right; its resolved sign is numerical tie-breaking, not a "
                "decision about an input)."
            )
        a("")
        if extracted:
            _offset_bisect_postlayout_delay_check(a, results)
        else:
            # Symmetry falsifiability: the same |Vindiff| on both signs should give
            # the same decision delay on a symmetric DUT. This is the check a sign
            # bug in the classification could not survive.
            a(
                "**4. Decision-delay symmetry, the falsifiability check.** On a "
                "symmetric mismatch-free DUT the decision delay at `+V` and `-V` "
                "must agree. Measured, per corner point (matched |Vindiff| pairs "
                "where both signs were probed):"
            )
            a("")
            a("| corner-id | matched pairs | worst |t(+V) - t(-V)| (ns) |")
            a("|---|---|---|")
            for r in results:
                by_v = {
                    round(p.vindiff_mv, 6): p.decide_time_ns for p in r.probes
                    if p.decide_time_ns is not None
                }
                deltas = [
                    abs(by_v[v] - by_v[round(-v, 6)])
                    for v in by_v
                    if v > 0 and round(-v, 6) in by_v
                ]
                if deltas:
                    a(f"| `{r.corner_id}` | {len(deltas)} | {max(deltas):.4f} |")
                else:
                    a(f"| `{r.corner_id}` | 0 | n/a |")
            a("")
            a(
                "A sign error in the polarity classification, or a one-sided "
                "search, could not produce a matched ladder -- which is why the "
                "coarse scan is a SYMMETRIC signed grid rather than a one-sided "
                "sweep."
            )
        a("")
        if extracted:
            a(
                "**5. What this does NOT say.** It does not bound the offset "
                "of a manufactured part: mismatch is disabled here by design, "
                "and the random term is large (see the pick-off record below). "
                "It does not generalize past the two PVT points measured, or "
                f"past the {BISECT_EVALUATE_NS} ns evaluate window. And the "
                "extracted netlist is quasi-static lumped R/C from `klt pex` "
                "(see 'Netlist scope' below) -- the post-layout netlist class "
                "this flow provides, not silicon, and not a distributed or "
                "substrate-coupled model."
            )
            a("")
            _offset_bisect_postlayout_comparison(a, results, half_lsb_mv)
        else:
            a(
                "**5. What this does NOT say.** It does not bound the offset of a "
                "manufactured part: mismatch is disabled here by design, and the "
                "random term is large (see the pick-off record below). It does not "
                "generalize past the two PVT points measured, or past the "
                f"{BISECT_EVALUATE_NS} ns evaluate window. And it says nothing "
                "about a post-layout DUT -- the cross-pollinated finding that "
                "prompted this measurement (issue #515) was taken on an EXTRACTED "
                "netlist and reported both a nonzero systematic offset at the "
                "nominal corner and a wide non-decision band at slow/cold. "
                + (
                    "**Neither shape appears at schematic level here**, which is "
                    "consistent with both being parasitic-driven."
                    if not offset_resolved and not resolved_bands else
                    "**At least one of those shapes DOES appear at schematic level "
                    "here** (see items 1-2 above), so it cannot be attributed to "
                    "parasitics in this block."
                )
                + " Either way this is a statement about netlist scope, not a "
                "refutation or a confirmation: this repo cannot replicate a "
                "post-layout result at all yet (see 'Methodology provenance' "
                "below), so nothing here tests what a parasitic extraction of this "
                "block would add."
            )
    else:
        a(
            "No corner point yielded a bounded pair of decision boundaries, so "
            "this record reports no systematic offset and no dead-band width. "
            "The per-corner status column and notes above say why, and that is "
            "the finding."
        )
        if extracted:
            a("")
            _offset_bisect_postlayout_comparison(a, results, half_lsb_mv)
    a("")

    for r in results:
        a(f"## Probe ladder -- `{r.corner_id}`")
        a("")
        a(
            "Every transient run at this corner point, in Vindiff order. The "
            "two outcome columns are the point of this record: `absolute "
            "outcome` is the resolved polarity on its own terms, `input-relative"
            "` renders the SAME probe in "
            "`RegenCornerPoint.classify()`'s taxonomy. A sign-corrected "
            "crossing test sees only the second column and cannot tell "
            "`WRONG-POLARITY` from `NO-DECISION` -- that conflation is what "
            "this subcommand exists to remove."
        )
        a("")
        a(
            "| Vindiff (mV) | absolute outcome | input-relative | "
            "t_decide (ns) | final v(OUTP)-v(OUTN) (V) | pre-edge diff (V) |"
        )
        a("|---|---|---|---|---|---|")
        for p in sorted(r.probes, key=lambda p: p.vindiff_mv):
            td = f"{p.decide_time_ns:.4f}" if p.decide_time_ns is not None else "--"
            fd = f"{p.final_diff_v:+.4f}" if p.final_diff_v is not None else "n/a"
            pe = f"{p.pre_edge_diff_v:+.4f}" if p.pre_edge_diff_v is not None else "n/a"
            a(
                f"| {p.vindiff_mv:+.6f} | {p.outcome} | {p.relative_outcome()} | "
                f"{td} | {fd} | {pe} |"
            )
        a("")
        if r.notes:
            for n in r.notes:
                a(f"- **Note (`{r.corner_id}`)**: {n}")
            a("")

    a("## Relationship to the pick-off record (`20260821-071918-433a294`)")
    a("")
    a(
        "That record measured a DIFFERENT quantity and is NOT superseded by "
        "this one: `tt_mm` mismatch corner, N=16 draws at Vindiff = 0, offset "
        "mean **35.2441 mV**, stdev **97.0825 mV**, range "
        "`[-136.4332, +224.9353] mV`, via the linearized pick-off statistic "
        f"(gain 4.2083 V/V fitted over ideal Vindiff in [1, 10] mV, pick-off at "
        f"evaluate_start + {PICKOFF_NS} ns). Its mean mixes the systematic term "
        "measured here with mismatch sampling noise; this record's probes have "
        "no mismatch in them at all."
    )
    a("")
    a(
        "The consistency check the two admit is on that mean. For N = 16 draws "
        "with sample stdev 97.0825 mV, the standard error of the sample mean is "
        "97.0825 / sqrt(16) = **24.2706 mV**, so the pick-off record's own "
        "estimate of the systematic (mean) term is 35.2441 +- 24.2706 mV -- "
        "i.e. **1.45 standard errors from zero**, which is not a detection of a "
        "systematic offset at all. A near-zero systematic boundary measured "
        "here is therefore CONSISTENT with that record rather than in tension "
        "with it, and the comparison is a statement about sample size, not "
        "about a disagreement between two methods."
        + (
            " (This record's DUT is the EXTRACTED netlist and that record's "
            "was schematic-level, so the comparison also crosses a netlist "
            "class; a sub-mV systematic boundary is still far inside that "
            "record's +-24.27 mV standard error either way.)"
            if extracted else ""
        )
    )
    a("")
    a(
        "Where they genuinely diverge is in what they CAN say. DR-004 Decision "
        "Sec.3 already flags that the pick-off magnitudes are an upper-bound / "
        "order-of-magnitude statistic for the larger draws, because the gain "
        "calibration is only validated for ideal Vindiff in [1, 10] mV and the "
        "largest draws extrapolate to ~225 mV where the relationship is "
        "compressive. The boundary measurement here has no calibration curve to "
        "fall outside of -- a boundary in Vindiff is decision-referred -- so it "
        "is the precise-extraction path DR-004's Open items asked for, taken by "
        "changing the question rather than by narrowing `PICKOFF_NS` or fitting "
        "a nonlinear curve (the two escalations DR-004 named). What it does NOT "
        "do is replace the sigma: it measures one DUT per corner, so it reports "
        "no spread. Bisecting the boundary per Monte Carlo draw -- a "
        "distribution of boundaries rather than a distribution of pick-off "
        "values -- is the natural next escalation and is named in DR-020's Open "
        "items, not attempted here."
    )
    a("")

    a("## Subset-corner justification (`sim/README.md`)")
    a("")
    a(
        f"This record runs {len(results)} PVT point(s) "
        f"({', '.join('`' + c + '`' for c in corner_ids)}), not the nine-point "
        "ratified one-at-a-time grid, and `ss`/-40 C is not even a point OF "
        "that grid: the ratified OAT star varies one axis at a time from "
        "`tt`/27 C/nominal, so it contains `ss`/27 C and `tt`/-40 C but never "
        "their combination. That combination is deliberate here and is the "
        "reason this record exists at these two points:"
    )
    a("")
    if extracted:
        a(
            "- **`tt`/27 C is the nominal point, NOT a negative control on this "
            "DUT.** On the schematic netlist it is one (symmetric by "
            "construction, so ~0 mV is forced); the extracted netlist is not "
            "symmetric by construction, so a non-zero answer here is a "
            "candidate circuit property. The measurement's own negative "
            "control is the same point on the schematic netlist, in "
            f"`{BISECT_SCHEMATIC_RECORD_ID}`."
        )
    else:
        a(
            "- **`tt`/27 C is the negative control.** A mismatch-free DUT at the "
            "nominal corner is symmetric in its input by construction, so its "
            "systematic boundary must come out at ~0 mV. A non-zero answer there "
            "would indict the measurement, not the comparator -- which is exactly "
            "what makes the `ss`/-40 C number trustworthy or not."
        )
    a(
        "- **`ss`/-40 C is the slow/cold stress point**, where regeneration is "
        "slowest and a finite evaluate window is most likely to produce a "
        "genuine non-decision band. It is the combination "
        "`2AMLogic/sky130-comparator`'s cross-pollinated finding reported "
        "(issue #515), and DR-004's Alternatives section names the slow/cold "
        "headroom margin as still-open for this block. Measuring the two axes "
        "separately would not have exercised it."
    )
    a(
        "- **The supply axis is not swept.** Both points run nominal "
        f"{VDD} V. A +-10% supply excursion moves the input common mode with "
        "the rail in this design (V_REF = V_DD, DR-003 Item 1), which is a "
        "different mechanism from the process/temperature one under test; "
        "adding it would double the cost without separating anything this "
        "record claims."
    )
    a(
        "- **Cost, against a session that must end.** Each probe is a full "
        f"{BISECT_EVALUATE_NS} ns transient at a 0.005 ns step, and a bisection "
        "to a 100 uV floor costs tens of them per corner point; the "
        f"{n_probes} probes here were run locally, ONE AT A TIME, in a single "
        "session on a shared dispatch worker where no process may outlive the "
        "session that started it (`.loom/docs/long-running-compute.md`). The "
        "sanctioned answer there is to scope the run to the session and land "
        "the increment, which is what this is. `offset-bisect --corner/--temp` "
        "runs any other point of the grid by accumulation."
    )
    a("")
    a(
        "So this is **not** a PVT-complete offset or dead-band figure and must "
        "not be quoted as one. It is a two-point measurement with its control "
        "point stated, sufficient for DR-020's spec-row question (does a row "
        "belong in the table at all?) and insufficient for a numeric bound on "
        "that row -- which is precisely why DR-020 does not set one."
    )
    a("")

    a("## Methodology provenance and clean-room note")
    a("")
    a(
        "The ALGORITHM SHAPE -- classify both polarities instead of a "
        "sign-corrected crossing test; bisect two boundaries over the input "
        "axis to separate a systematic offset from a non-decision band; treat "
        "near-boundary solver crawl as a budget floor rather than a circuit "
        "outcome -- is cross-pollinated methodology from the sibling canary "
        "`2AMLogic/sky130-comparator` "
        "([issue #66](https://github.com/2AMLogic/sky130-comparator/issues/66), "
        "[PR #119](https://github.com/2AMLogic/sky130-comparator/pull/119)), "
        "reported into this repo as `2AMLogic/sky130-sar-adc` issue #515."
    )
    a("")
    a(
        "Only that shape crosses the boundary. The implementation here is "
        "re-derived against THIS repo's own primitives -- `_regen_deck()`'s "
        "stimulus, `RESET_HOLD_TOLERANCE_FRAC`'s reset-integrity rule, "
        "`RegenCornerPoint.classify()`'s outcome taxonomy, DR-003 Item 3's "
        "differential LSB -- and no netlist, sizing, device, corner choice, or "
        "measured VALUE from that repo is introduced or reconstructed, per "
        "`CLAUDE.md`'s clean-room / no-reverse-engineering rule. Issue #515 "
        "records that the sibling's own `offset-bisect` implementation was "
        "described secondhand and never inspected; nothing above depends on "
        "what it does."
    )
    a("")
    if dut_fragment == DUT_FRAGMENT_EXTRACTED:
        a(
            "**Netlist scope.** Every probe runs the post-layout extracted "
            f"fragment `{dut_fragment.relative_to(evidence.REPO_ROOT)}` -- the "
            "comparator sub-block's `klt pex` extraction (82 R/C elements, "
            "star-model per-net R, net-to-ground and vertical-overlap "
            "coupling C; quasi-static) wrapped in one instantiation line. "
            "Compare against the schematic-level record "
            "`sim/comparator-decision/records/20261002-203719-c898d06.md`, "
            "taken with the same stimulus and search. The extraction is of "
            "the DR-004 Amendment A layout (`eace0b6`). Re-checked for issue "
            "#525 by diffing `layout/comparator/bin/` from `eace0b6` to this "
            "record's commit: the only generator changes move the tap/licon "
            "drawing into `layout/bin/_geometry_common.tap_shapes()` with the "
            "same layers and 0.60 um pitch, and dedup the `klt gen` "
            "invocation -- no drawn-geometry change -- and "
            "`design/comparator.sch` is unchanged over the same range. "
            "Quasi-static "
            "lumped R/C does not model distributed or substrate-coupled "
            "effects, so this is the post-layout netlist class the flow "
            "provides, not silicon."
        )
    else:
        a(
            "**Netlist scope, stated because the cross-pollinated finding was "
            "post-layout and this is not.** Every probe runs the "
            "schematic-derived fragment "
            f"`{DUT_FRAGMENT.relative_to(evidence.REPO_ROOT)}` (netlisted from "
            "`design/comparator.sch` via xschem), NOT an extracted netlist. The "
            "comparator's own layout extraction is DRC/LVS-clean but device-level "
            "only -- `layout/comparator/reports/LATEST`'s record states it is not a "
            "parasitic extraction -- so a post-layout replication of the sibling's "
            "specific result is not possible in this repo yet and is not attempted. "
            "That is a scope statement, not a null result: a systematic offset and "
            "a dead band are both quantities the schematic-level DUT has in its own "
            "right, and DR-004's Open items asked for them at this level."
        )

    a("")
    return _finalize_record(
        lines, record_path, prov.pdk_line, prov.ng_version, prov.netlist_sha,
        "offset-bisect", supersedes=supersedes,
    )

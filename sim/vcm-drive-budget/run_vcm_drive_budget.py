#!/usr/bin/env python3
"""VCM drive-impedance / decoupling budget for the sampling front end
(issue #121, Epic #542 Phase 4B follow-up).

`docs/chipalooza/challenge-4-proposal.md` (`docs/chipalooza/challenge-4-proposal.md`,
PR #140) named an open item: every testbench in this repo drives `VCM` from
an ideal (zero-impedance) source, so the design has never quantified how much
real (non-zero) drive resistance and/or on-die decoupling `VCM` needs to
preserve the sampling front end's own already-verified sub-mV in-sample
settling (`sim/sampling-frontend/records/20260821-072657-433a294.md`).

This script answers that, at a single corner (tt/27C/1.8V, deferred full-PVT
per the same precedent `sim/sampling-frontend/run_hold_kick.py` Experiments
1-5 set), by reusing the unmodified sampling front-end DUT fragment
(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, read in
place -- not duplicated, matching `run_hold_kick.py`'s own precedent for
`CDAC_FRAGMENT`) and replacing its ideal `Vvcm` source with an ideal source
in series with a swept resistance `R_source` (representing whatever off-chip
or on-chip reference buffer / pad network actually drives the shared `VCM`
net in silicon), optionally with a decoupling capacitor `C_decouple` at the
on-die `VCM` node.

Both `Cmswn_{p,n}`/`Cmswp_{p,n}` switches (the front end's common-mode /
reference-switching transmission gates, `design/sampling_frontend.sch`'s own
comment block) tie to the SAME `VCM` net for both differential legs
(confirmed directly from the DUT fragment: all four switch instances name
node `VCM`), so `R_source` sees the combined current draw of both legs
charging `BPREF_P`/`BPREF_N` back toward `VCM` every SAMPLE assertion -- the
realistic shared-rail case, not two independently driven half-circuits.

**What "acquisition window" means here.** `spec/decision-records/DR-006-sar-
sequencer-bit-count-and-timing-budget.md` derives `f_clk = 12 * f_s` from the
DRAFT 100 kS/s-1 MS/s sample-rate row and a uniform one-`CLK`-period SAMPLE
phase, i.e. `t_sample = 1 / f_clk`:

  - `t_sample_worst_ns` = 1e3 / 12 MHz  = 83.33 ns  (fastest provisional clock
    -- the SHORTEST window, i.e. the case least forgiving of a slow VCM)
  - `t_sample_slow_ns`  = 1e3 / 1.2 MHz = 833.3 ns (slowest provisional clock)

Every prior sampling-frontend record (`run_transient.py`, `run_hold_kick.py`)
used a fixed testbench convention of 400 ns for the SAMPLE pulse width,
independent of DR-006 -- itself never previously reconciled against the
DRAFT clock-rate row. This script tests BOTH the DR-006-derived worst-case
window (83.33 ns) and the repo's existing 400 ns testbench convention, so the
two are for the first time shown side by side.

No claim here is graded against a ratified spec row: `spec/target-spec.md`
is entirely DRAFT (#1/#27), `LSB_DIFF_MV_PROVISIONAL` is quoted only as a
reference scale (same convention `run_hold_kick.py` already established), and
the DR-006 timing window is itself downstream of the DRAFT sample-rate row
(the gap `docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 already
names). What this DOES produce, for the first time, is a concrete R_source /
C_decouple relationship the design can be checked against once any of those
upstream numbers ratify.

FULL-PVT-GRID MODE (``--corners``, added 2026-09-07). The single-corner
caveat above ("switch R_on varies materially with process/temperature, so a
full PVT sweep of this same budget is still open") is what this mode exists
to close for the bare (undecoupled) R_source budget: it re-runs that one
sweep (the ``worst_case_pp`` test point) at the same ratified 9-point
one-at-a-time (OAT) PVT grid every other
``docs/chipalooza/challenge-4-proposal.md`` Section 7 Item 2 mechanism
campaign now sweeps (process ``{ff, fs, sf, ss, tt}`` x temperature
``{-40, 27, 125} C`` x supply ``{1.62, 1.8, 1.98} V``,
``spec/target-spec.md``'s "Numeric rows -- RATIFIED 2026-08-19" section).
A new ``--window {worst,legacy}`` selector (added 2026-09-07, alongside
``--corners``) chooses which acquisition window's bare R_source sweep is
repeated per corner:

  - ``worst`` (default): the DR-006 worst-case (12 MHz, 83.333 ns) window,
    the full ``R_SOURCE_SWEEP_OHM`` list.
  - ``legacy``: this repo's pre-existing 400 ns testbench convention, the
    reduced ``R_SOURCE_SWEEP_LEGACY_OHM`` list (same reduced-runtime
    rationale as the single-corner default path's own legacy sweep). The
    single-corner record already found the legacy window to be the MORE
    demanding case for this mechanism, not the worst-case window -- this
    mode is what closes that finding's own "not yet corner-complete" gap.

Only one window is swept per invocation.

A second selector, ``--sweep {rsource,decouple}`` (added 2026-09-07), chooses
which *leg* of the budget ``--corners`` repeats per corner:

  - ``rsource`` (default): the bare (undecoupled) R_source sweep described
    above.
  - ``decouple``: the C_decouple sweep -- the last leg of this budget that
    was still single-corner-only. Each corner is decoupled against its OWN
    marginal R_source (``marginal_r_source()``, re-derived from that same
    corner's own bare sweep in the same invocation), never a value borrowed
    from the ``tt``/27C/1.8V point, because the bare budget itself is already
    known to vary by more than an order of magnitude across the grid
    (``records/20260907-052526-f589273.md``). The bare sweep therefore still
    runs per corner in this mode; only the reported leg differs.

Nothing about the single-corner default path above is changed;
``--corners``/``--window``/``--sweep`` are purely additive.

HOW ``--corners`` EXECUTES: ``klt sim``, NOT A LOCAL ngspice LOOP (issue
#881, 2026-11-13). Both ``--corners`` legs used to run their grid as an
in-process ``ngspice`` loop, one subprocess per (corner, swept value) -- 72
solves for the worst-window bare sweep, 117 for its decouple sibling.
CLAUDE.md's host rule forbids a hand-launched grid on this shared dispatch
worker, so the four full-PVT-grid records this mode minted could not be
re-run at all as the driver stood. Each ``--corners`` invocation is now ONE
``klt sim`` request submitted to the batch fleet through
``sim/harness/klt_sim.py`` (which passes ``--wait-for-capacity 600``), one
unit per corner, every swept value an ``analysis_steps[]`` entry inside that
unit -- the pattern
``sim/input-drive-budget/run_input_drive_budget.py`` established. The
single-corner default path is unchanged and still runs locally, which is
what it is: one unit.

One shared deck body cannot bake a corner's supply into a literal the way a
regenerated per-corner deck can, so the port made four deck changes (the
supply-tracking ``VCM`` and ``SAMPLE`` sources, the ``vsup`` element name the
corner axis alters, and an always-present ``Cdecouple`` card whose
``C_decouple = 0`` control row is a negligible capacitance rather than an
omitted card). All four are listed in ``DECK_PORT_CHANGES`` and restated in
every record this path mints, beside the PDK-commit, simulator-version and
execution-route differences against the record each one supersedes. ``--probe``
is the single-unit control that separates those deck changes from the rest:
one corner, one swept resistance, the ported deck and the pre-port
``build_transient()`` deck run against each other on the SAME host and PDK.

    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --dry-run
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --probe
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --record
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --window legacy --record
    python3 sim/vcm-drive-budget/run_vcm_drive_budget.py --corners --sweep decouple --record
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
EXPERIMENT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SIM_DIR))
from harness import (  # noqa: E402
    corners as corners_mod,
    evidence,
    klt_sim,
    measure,
    toolchain,
)

DUT_FRAGMENT = (
    SIM_DIR / "sampling-frontend" / "testbench" / "sampling_frontend_dut.spice"
)

# The repo-relative path every record's `Written by` footer must name (issue
# #274). Every other runner under sim/ already passes its own repo-relative
# path to evidence.footer_lines(); this script passed the bare file name, so
# its ten committed records name `run_vcm_drive_budget.py` with no directory.
# sim/check_spec_coverage.py resolves that bare name against the record's own
# experiment directory (same_runner()), so those records stay indexable; every
# record minted from here on carries the unambiguous path instead.
WRITTEN_BY = "sim/vcm-drive-budget/run_vcm_drive_budget.py"

VDD_NOM = 1.8
VCM_FRAC = 0.5  # VCM = VCM_FRAC * VDD (DR-003 Item 1, provisional)
LSB_DIFF_MV_PROVISIONAL = 3.5156  # DR-003 Item 2, provisional pending #27

# DR-006-derived acquisition (SAMPLE-high) windows: t_sample = 1 / f_clk,
# f_clk = 12 * f_s, f_s in the DRAFT 100 kS/s-1 MS/s row.
T_SAMPLE_WORST_NS = 1.0e3 / 12.0   # 83.333... ns @ f_clk_max = 12 MHz
# Existing repo-wide sampling-frontend testbench convention (run_transient.py
# / run_hold_kick.py), independent of DR-006 -- kept for direct comparison.
T_SAMPLE_LEGACY_NS = 400.0

SAMPLE_TD_NS = 10.0   # SAMPLE rising edge start
SAMPLE_TR_NS = 1.0    # SAMPLE rise/fall time
TRAN_STEP_PS = 10.0   # matches run_hold_kick.py's converged step (see its
                      # own Experiment 5 / TRAN_STEP_PS comment)

TEST_POINTS = {
    "common_mode": (0.9, 0.9),
    "worst_case_pp": (1.6, 0.2),
}
DEFAULT_POINT = "worst_case_pp"

# R_source sweep: 0 (today's implicit ideal-source assumption) through a
# clearly-undriven pad-scale impedance. Log-spaced to resolve where the
# error transitions from negligible to LSB-scale.
R_SOURCE_SWEEP_OHM = [0.0, 100.0, 300.0, 1e3, 3e3, 10e3, 30e3, 100e3]
# The legacy (400 ns) window's tran runs cover ~5x more simulated time than
# the worst-case (83.3 ns) window's; a reduced subset keeps this script's
# total runtime bounded on a shared/contended machine (see
# toolchain.run_ngspice_with_retry()'s docstring) while still bracketing
# the same order-of-magnitude transition
# the full sweep above resolves for the worst-case window.
R_SOURCE_SWEEP_LEGACY_OHM = [0.0, 10e3, 100e3]

# Decoupling-capacitor values tested at a fixed, marginal R_source (chosen
# after the bare sweep above identifies it) to quantify how much on-die/at-
# pad decoupling relaxes the bare-R_source budget.
C_DECOUPLE_SWEEP_F = [0.0, 1e-12, 10e-12, 100e-12, 1e-9]

# ---------------------------------------------------------------------------
# --corners execution constants: ONE `klt sim` request per invocation (#881)
# ---------------------------------------------------------------------------
#: The `corners.supply_v` axis key. `klt sim` applies that axis as a literal
#: `alter <key>=<value>`, so the key IS the supply source's element name -- a
#: key naming no element is refused, and a mismatch would otherwise simulate
#: the nominal supply at every corner. The `--corners` deck body therefore
#: declares the supply source under this exact name
#: (sim/input-drive-budget/run_input_drive_budget.py's own convention).
SUPPLY_KEY = "vsup"

#: The resistance actually emitted for the `R_source = 0` control row.
#: `build_transient()` already used this literal, for the reason stated at
#: its own call site (a 0-ohm resistor is an ngspice singular-matrix /
#: convergence footgun on some ngspice versions). It is named here because
#: the `klt sim` steps `alter` the same card and must emit the same value.
R_IDEAL_OHM = 1.0e-6

#: The capacitance emitted for the `C_decouple = 0` control row of the
#: `--corners --sweep decouple` request.
#:
#: `build_transient()` OMITS the `Cdecouple` card entirely when
#: `C_decouple = 0`; a `klt sim` step can only `alter` a card the one shared
#: deck body already carries, so the card is present in EVERY step and the
#: control row is a negligible capacitance instead of an absent card. 1 aF
#: is six orders of magnitude below the smallest swept value (1 pF) and far
#: below the `VCM` node's own device parasitics, so it is an open circuit to
#: the precision anything here is read at -- the same stand-in shape
#: `R_IDEAL_OHM` already has on the resistance axis. This is a deck
#: difference from the records a `--corners` re-run supersedes, and every
#: record this path mints states it (see `DECK_PORT_CHANGES`).
C_IDEAL_F = 1.0e-18

#: Per-unit `options.timeout_s` for a `--corners` submission. NOT a free
#: parameter: the batch fleet refuses a job whose CONSERVATIVE FULLY-SERIAL
#: bound -- `timeout_s * units + 120` -- exceeds its own whole-job ceiling
#: (`max_job_seconds`, 3600 s when this was written), which with 9 corner
#: units caps `timeout_s` at about 386 s. 300 s holds the whole-job bound at
#: 2820 s, inside the ceiling. The largest unit this driver submits is the
#: worst-window `decouple` one at 36 tran steps; each record's `klt sim` run
#: block reports the per-corner `runtime_s` the fleet actually measured, so
#: the headroom is checkable rather than asserted. Raising this is not free
#: -- check it against the ceiling and the unit count first, or the submit
#: is refused before anything runs.
DEFAULT_TIMEOUT_S = 300.0

#: CLAUDE.md's fleet rule: the fleet is vCPU-budgeted, so a burst is refused
#: with `batch_no_capacity` unless the submit may wait with backoff. Applied
#: by `harness.klt_sim.submit_argv()` on every non-local submit, shared with
#: every other batch campaign (issue #865).
CAPACITY_WAIT_S = klt_sim.DEFAULT_CAPACITY_WAIT_S

SubmitError = klt_sim.SubmitError

#: Every way the one shared `--corners` deck body differs from the per-corner
#: deck `build_transient()` regenerates, stated in each record this path
#: mints so a reader comparing a new record against the one it supersedes can
#: see what changed besides the PDK and simulator versions. Each entry is a
#: consequence of "one deck body, corner applied as an axis" -- see
#: `build_corners_body()`.
DECK_PORT_CHANGES = [
    "**Supply-tracking `VCM` source.** The per-corner deck wrote `VCM`'s "
    "ideal level as a literal (`dc {vdd * VCM_FRAC}`) because it regenerated "
    "a deck per corner. One shared body cannot, so `VCM_IDEAL` is driven by "
    "a behavioural source `Bvcm VCM_IDEAL 0 V=v(VDD)*VCM_FRAC`, which "
    "evaluates to the same level at every corner the grid runs.",
    "**Supply-tracking `SAMPLE` source.** Likewise `pulse(0 {vdd} ...)` "
    "becomes a NORMALISED 0..1 `pulse` on `SMP_CTL` scaled by the corner's "
    "own supply through `Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)` -- the same "
    "device `sim/input-drive-budget/run_input_drive_budget.py` uses for its "
    "own SAMPLE control, and for the same reason.",
    "**The supply source is named `vsup`.** `klt sim` applies the "
    "`corners.supply_v` axis as a literal `alter <key>=<value>`, so the key "
    "is the element name; the per-corner deck called it `Vdd`.",
    "**The `C_decouple = 0` control row is a 1 aF capacitor, not an omitted "
    "card.** A step can only `alter` a card the shared body already carries, "
    "so `Cdecouple` is present in every step (see `C_IDEAL_F`). The "
    "per-corner deck omitted it entirely at `C_decouple = 0`.",
    "**`.options num_threads=1`.** Added so a multi-core fleet worker solves "
    "the deck the same way a single-threaded local run does; the per-corner "
    "deck carried no `.options` card.",
]

# Ratified corner-set axes (issue #28), per spec/target-spec.md's "Numeric
# rows -- RATIFIED 2026-08-19" section: -40/27/125C, +-10% supply, sky130
# process corners -- the same axes every other Section 7 Item 2 mechanism
# campaign (sim/cdac-bit-trial-settling/, sim/comparator-decision/,
# sim/sequencer-logic-delay/, sim/sampling-acquisition-settling/) sweeps.
# Used only by the optional --corners mode below; the single-corner
# (tt/27C/1.8V) default behavior above is unchanged.
SUPPLY_TOLERANCE = corners_mod.RATIFIED_SUPPLY_TOLERANCE
TEMPS_C = corners_mod.RATIFIED_TEMPS_C
PROCESS_CORNERS = corners_mod.RATIFIED_PROCESS_CORNERS

# The single-corner (tt/27C/1.8V) record --corners's own evidence record
# cross-references as "the finding this campaign extends".
SINGLE_CORNER_SEED_RECORD = "20260905-201703-f012255"

# issue #248: the four pre-issue-#236 --corners-mode records, one per
# (--sweep, --window) combination, that this same combination's post-#236
# re-run supersedes. All four were measured against the SAME pre-#236 DUT
# netlist sha256 as SINGLE_CORNER_SEED_RECORD -- itself already superseded by
# issue #245's single-corner re-run (records/20260908-074408-80df05e.md) --
# but #245 explicitly scoped only the single-corner default path, leaving
# these four full-PVT-grid records stale until now.
CORNERS_SUPERSEDES_RECORD = {
    ("rsource", "worst"): "20260907-052526-f589273",
    ("rsource", "legacy"): "20260907-090200-7768162",
    ("decouple", "worst"): "20260907-104958-a546200",
    ("decouple", "legacy"): "20260908-021006-f48a228",
}

# The CURRENT full-PVT-grid record per (--sweep, --window) as of issue #881:
# the four records the `klt sim` port's own re-runs displace. Used ONLY to
# report the uncontrolled differences between a new record and the one it
# supersedes (PDK commit, simulator version) -- and the PDK/ngspice figures
# are READ OUT OF THAT RECORD'S OWN Environment BLOCK by
# predecessor_environment() below, never transcribed here, so this map
# cannot drift from the records it names.
#
# Like CORNERS_SUPERSEDES_RECORD above this is a fixed historical fact, not a
# self-updating pointer: a later re-run that displaces a DIFFERENT record
# must update this map alongside its own `--supersedes` (issue #513's same
# contract). `records/LATEST` is not used for it, because LATEST names
# whichever record is newest across all four combinations, not the one this
# combination displaces.
CORNERS_PREDECESSOR_RECORD = {
    ("rsource", "worst"): "20260908-100413-f3e2914",
    ("rsource", "legacy"): "20260908-101358-f3e2914",
    ("decouple", "worst"): "20260908-113002-f3e2914",
    ("decouple", "legacy"): "20260908-115336-f3e2914",
}

_ENV_PDK_RE = re.compile(r"^- PDK: (.+)$", re.M)
_ENV_NGSPICE_RE = re.compile(r"^- ngspice: (.+)$", re.M)


def predecessor_environment(sweep: str, window: str,
                            records_dir: Path | None = None) -> dict:
    """`{"record": <id>, "pdk": ..., "ngspice": ...}` for the record a
    `--corners` re-run of this (`sweep`, `window`) combination displaces.

    The PDK commit and simulator version are parsed out of that record's own
    `## Environment` block rather than copied into this file, so the
    "uncontrolled differences" statement a new record carries is read from
    the evidence it is being compared against. A missing record, or a record
    whose Environment block cannot be parsed, yields `None` for the field --
    the record writer then says the comparison could not be made rather than
    inventing one."""
    record_id = CORNERS_PREDECESSOR_RECORD[(sweep, window)]
    records_dir = records_dir or (EXPERIMENT_DIR / "records")
    path = records_dir / f"{record_id}.md"
    text = path.read_text() if path.is_file() else ""
    pdk_hit = _ENV_PDK_RE.search(text)
    ng_hit = _ENV_NGSPICE_RE.search(text)
    return {
        "record": record_id,
        "pdk": pdk_hit.group(1).strip() if pdk_hit else None,
        "ngspice": ng_hit.group(1).strip() if ng_hit else None,
    }


# Per-`--sweep` description of what a --corners pass repeats at every corner,
# spliced into the default supersession narrative below.
CORNERS_SWEEP_DESCRIPTION = {
    "rsource": "bare (undecoupled) R_source sweep at the {window} window",
    "decouple": (
        "C_decouple sweep at the {window} window (each corner at its own "
        "marginal R_source)"
    ),
}


def default_corners_supersedes(sweep: str, window: str) -> str:
    """The DEFAULT **Supersedes** narrative for a `--corners --sweep <sweep>
    --window <window>` record: the pre-issue-#236 record of that same
    combination, from CORNERS_SUPERSEDES_RECORD above.

    A default, not the only possible value (issue #513). What it names is a
    fixed historical fact -- the record this combination displaced ONCE, in
    September 2026 -- so the next re-run of the same combination would
    otherwise claim to supersede the record BEFORE the one it actually
    displaces. `--supersedes` overrides it; omitting the flag reproduces the
    pre-#513 bytes exactly, so no committed record is affected."""
    old_id = CORNERS_SUPERSEDES_RECORD[(sweep, window)]
    swept = CORNERS_SWEEP_DESCRIPTION[sweep].format(window=window)
    return (
        f"[`records/{old_id}.md`]({old_id}.md) -- same full ratified "
        f"PVT-grid {swept}, measured against the pre-issue-#236 "
        "`design/sampling_frontend.sch` (`Sa_p`/`Sa_n`'s gate on `SAMPLE`, "
        "`Cmswn`/`Cmswp` at `W=1um`). This record re-runs the identical "
        "sweep against the post-#236 DUT fragment (`Sa_p`/`Sa_n`'s gate "
        "moved to `G_P`/`G_N`; `Cmswn`/`Cmswp` widened to `W=16um` -- issue "
        "#236, re-verified in layout as #245), closing the follow-up issue "
        "#245 itself explicitly deferred (issue #248). This record's own DUT "
        "netlist sha256 (below) differs from the superseded record's, "
        "confirming the fix is actually reflected, not a no-op re-run "
        "against a cached fragment."
    )


# --corners --window {worst,legacy}: (sample_width_ns, r_source_sweep_list)
# per window. "worst" is the DR-006-derived worst-case (12 MHz) acquisition
# window at the full R_SOURCE_SWEEP_OHM resolution; "legacy" is this repo's
# pre-existing 400 ns testbench convention at the reduced
# R_SOURCE_SWEEP_LEGACY_OHM resolution (same runtime-bounding rationale as
# the single-corner default path's own legacy sweep, see
# R_SOURCE_SWEEP_LEGACY_OHM above).
WINDOW_CONFIG = {
    "worst": (T_SAMPLE_WORST_NS, R_SOURCE_SWEEP_OHM),
    "legacy": (T_SAMPLE_LEGACY_NS, R_SOURCE_SWEEP_LEGACY_OHM),
}
WINDOW_DESCRIPTION = {
    "worst": f"DR-006 worst-case (12 MHz, {T_SAMPLE_WORST_NS:.3f} ns)",
    "legacy": f"legacy ({T_SAMPLE_LEGACY_NS:.1f} ns) testbench convention",
}
# Bare (undecoupled) 1-LSB R_source budget the single-corner
# (tt/27C/1.8V) seed record (SINGLE_CORNER_SEED_RECORD) reports per window
# -- read directly from that record's own "## Result" section, used only to
# phrase this campaign's own "tightens vs. the single-corner finding" note.
# `None` is that record's "<= 0 ohm" figure restated in this script's
# post-#874 convention: `find_budget()` no longer counts the R_source = 0
# control row, so "the only point inside 1 LSB is the ideal-source baseline
# itself" is now reported as no positive budget rather than as a budget of
# zero. The seed record itself is untouched append-only evidence -- this is
# a reading of it, not an edit to it.
SINGLE_CORNER_SEED_BUDGET_1LSB_OHM: dict[str, float | None] = {
    "worst": 10e3,
    "legacy": None,
}

# The DEFAULT **Supersedes** narrative for the single-corner (default-path)
# record -- same "default, not only value" contract as
# default_corners_supersedes() above (issue #513), overridable with
# --supersedes.
#
# The four --corners-mode records this narrative calls out are no longer
# awaiting a re-derivation: issue #248 (the follow-up #245 deferred) closed
# 2026-09-08, and each of the four is now superseded by its own post-#236
# --corners re-run -- which is why this text states that rather than the
# "not-yet-done" it said while #248 was open.
SINGLE_CORNER_SUPERSEDES_DEFAULT = (
    f"[`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
    f"({SINGLE_CORNER_SEED_RECORD}.md) -- same single-corner "
    "(tt/27C/1.8V) default-path measurement (worst-case/legacy "
    "R_source sweeps + the marginal-R_source C_decouple sweep), "
    "re-run against design/sampling_frontend.sch post-issue-#236 "
    "(Sa_p/Sa_n's gate moved from SAMPLE to G_P/G_N; Cmswn/Cmswp "
    "widened from W=1um to W=16um -- issue #245). That record's own "
    "DUT netlist sha256 differs from this record's own (below), "
    "confirming the DUT fragment actually changed between the two "
    "runs, not just the record id. Issue #245 explicitly scoped "
    "only this single-corner default path's re-run; the four "
    "pre-#236 --corners-mode records "
    "(20260907-052526-f589273, 20260907-090200-7768162, "
    "20260907-104958-a546200, 20260908-021006-f48a228) were "
    "measured against the SAME pre-#236 DUT netlist sha256 as "
    f"{SINGLE_CORNER_SEED_RECORD} and were therefore also stale; "
    "re-deriving them over the full PVT grid was the separate "
    "follow-up issue #248, since done -- each is superseded by its "
    "own post-#236 --corners re-run (respectively "
    "20260908-100413-f3e2914, 20260908-101358-f3e2914, "
    "20260908-113002-f3e2914, 20260908-115336-f3e2914), by those "
    "records rather than by this one."
)


def build_transient(
    *,
    vinp: float,
    vinn: float,
    sample_width_ns: float,
    r_source_ohm: float,
    c_decouple_f: float = 0.0,
    corner: str = "tt",
    temp_c: float = 27.0,
    vdd: float = VDD_NOM,
    tran_step_ps: float = TRAN_STEP_PS,
) -> str:
    """One transient deck: the unmodified sampling-frontend DUT fragment,
    with its ideal Vvcm source replaced by an ideal source in series with
    R_source into the on-die VCM net (plus an optional decoupling cap at
    that same node). SAMPLE is a single pulse `sample_width_ns` wide,
    starting at SAMPLE_TD_NS; the measurement of interest is the sampled
    TOP_x value at the END of that window (t = SAMPLE_TD_NS + SAMPLE_TR_NS +
    sample_width_ns - one step), i.e. the instant SAR-ADC decision would
    actually see."""
    vcm = round(vdd * VCM_FRAC, 6)
    sample_end_ns = SAMPLE_TD_NS + SAMPLE_TR_NS + sample_width_ns
    probe_ns = sample_end_ns - (tran_step_ps / 1000.0) * 2
    tran_stop_ns = sample_end_ns + 50.0

    lines = toolchain.deck_preamble(
        corner, temp_c,
        f"issue #121 VCM drive-budget -- corner={corner} temp={temp_c}C "
        f"vdd={vdd} vinp={vinp} vinn={vinn} r_source={r_source_ohm:g} "
        f"c_decouple={c_decouple_f:g} sample_width_ns={sample_width_ns:g}",
    )
    lines += [
        f"Vdd VDD 0 dc {vdd}",
        f"Vinp VINP 0 dc {vinp}",
        f"Vinn VINN 0 dc {vinn}",
        f"Vvcm_ideal VCM_IDEAL 0 dc {vcm}",
    ]
    if r_source_ohm > 0:
        lines.append(f"Rvcm VCM_IDEAL VCM {r_source_ohm:.6g}")
    else:
        # R_source = 0 is the pre-existing ideal-source baseline (identical
        # to run_transient.py / run_hold_kick.py's own Vvcm), kept as a
        # literal wire rather than a 0-ohm resistor to avoid an ngspice
        # singular-matrix / convergence footgun on some ngspice versions.
        lines.append(f"Rvcm VCM_IDEAL VCM {R_IDEAL_OHM:g}")
    if c_decouple_f > 0:
        lines.append(f"Cdecouple VCM 0 {c_decouple_f:.6g}")
    lines.append(
        f"Vsample SAMPLE 0 pulse(0 {vdd} {SAMPLE_TD_NS}n {SAMPLE_TR_NS}n "
        f"{SAMPLE_TR_NS}n {sample_width_ns}n {tran_stop_ns * 10}n)"
    )
    lines += ["", DUT_FRAGMENT.read_text(), ""]

    meas = [
        ("top_p_end", "TOP_P", probe_ns),
        ("top_n_end", "TOP_N", probe_ns),
        ("bp_p_end", "BPREF_P", probe_ns),
        ("bp_n_end", "BPREF_N", probe_ns),
        ("vcm_end", "VCM", probe_ns),
    ]
    lines.append(".control")
    lines.append(f"tran {tran_step_ps}p {tran_stop_ns}n")
    for name, node, at_ns in meas:
        lines.append(f"meas tran {name} find v({node}) at={at_ns}n")
    lines += [".endc", ".end"]
    return "\n".join(lines) + "\n"


MEASURE_NAMES = ["top_p_end", "top_n_end", "bp_p_end", "bp_n_end", "vcm_end"]


def _run(netlist: str, scratch: Path, tag: str) -> dict[str, float]:
    """Retry policy documented once in toolchain.run_ngspice_with_retry()."""
    return measure.parse(
        toolchain.run_ngspice_with_retry(netlist, scratch, tag), MEASURE_NAMES
    )


def run_sweep(point: str, sample_width_ns: float, window_label: str,
              scratch: Path,
              r_source_list: list[float] | None = None,
              corner: str = "tt", temp_c: float = 27.0, vdd: float = VDD_NOM,
              quiet: bool = False) -> list[dict]:
    vinp, vinn = TEST_POINTS[point]
    rows = []
    baseline = None
    for r_source in (r_source_list if r_source_list is not None
                     else R_SOURCE_SWEEP_OHM):
        m = _run(
            build_transient(vinp=vinp, vinn=vinn,
                            sample_width_ns=sample_width_ns,
                            r_source_ohm=r_source,
                            corner=corner, temp_c=temp_c, vdd=vdd),
            scratch,
            f"rsweep_{window_label}_{point}_{corner}_{temp_c:g}_{vdd:g}_{r_source:g}",
        )
        diff = m["top_p_end"] - m["top_n_end"]
        row = {"r_source_ohm": r_source, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
        if not quiet:
            print(
                f"[{window_label:6}] {point:14} R_source={r_source:9.0f} ohm  "
                f"VCM(end)={m['vcm_end']:.4f} V  "
                f"diff_err={row['diff_err_mv']:+8.4f} mV "
                f"({row['diff_err_lsb']:+7.4f} LSB)"
            )
    return rows


def run_decouple_sweep(point: str, sample_width_ns: float, window_label: str,
                        r_source_ohm: float, scratch: Path,
                        corner: str = "tt", temp_c: float = 27.0,
                        vdd: float = VDD_NOM,
                        quiet: bool = False) -> list[dict]:
    vinp, vinn = TEST_POINTS[point]
    rows = []
    baseline = None
    for c_decouple in C_DECOUPLE_SWEEP_F:
        m = _run(
            build_transient(vinp=vinp, vinn=vinn,
                            sample_width_ns=sample_width_ns,
                            r_source_ohm=r_source_ohm,
                            c_decouple_f=c_decouple,
                            corner=corner, temp_c=temp_c, vdd=vdd),
            scratch,
            f"csweep_{window_label}_{point}_{corner}_{temp_c:g}_{vdd:g}_"
            f"{r_source_ohm:g}_{c_decouple:g}",
        )
        diff = m["top_p_end"] - m["top_n_end"]
        row = {"c_decouple_f": c_decouple, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
        if not quiet:
            print(
                f"[{window_label:6}] {point:14} R_source={r_source_ohm:.0f} ohm "
                f"C_decouple={c_decouple * 1e12:7.1f} pF  "
                f"VCM(end)={m['vcm_end']:.4f} V  "
                f"diff_err={row['diff_err_mv']:+8.4f} mV "
                f"({row['diff_err_lsb']:+7.4f} LSB)"
            )
    return rows


def find_budget(rows: list[dict], threshold_lsb: float) -> dict | None:
    """The ROW for the largest R_source (or C_decouple boundary) in `rows`
    for which abs(diff_err_lsb) stays under `threshold_lsb` -- None if even
    the first non-zero point already exceeds it, and the max swept value's
    row if every point stays under (a right-censored bound, reported as
    such).

    `rows[0]` -- the CONTROL row -- is excluded from the candidates (issue
    #874). Both `run_sweep()` and `run_decouple_sweep()` seed their baseline
    from their own first row, so that row's `diff_err_lsb` is identically
    zero by construction and would otherwise pass every threshold: "no swept
    value works" would be reported as a budget of "<= 0 ohm" / "<= 0.00 pF",
    which reads as a measurement but only restates the arithmetic. Excluding
    it is what makes the None result above reachable at all -- before #874
    this function could not return None, and every caller branch that
    reports "none found" / "unrescued" was dead.

    This mirrors `sim/input-drive-budget/run_input_drive_budget.py`'s own
    `find_budget()` (whose docstring recorded that this implementation's None
    branch was unreachable), with one deliberate difference: the control row
    is excluded POSITIONALLY rather than by `r_source_ohm > 0`, because this
    driver applies the same helper to the C_decouple axis (`c_decouple_f`)
    as well as the R_source axis, and in both cases the control row is the
    sweep's own first row by construction. Covered by
    sim/tests/test_run_vcm_drive_budget.py."""
    ok = [r for r in rows[1:] if abs(r["diff_err_lsb"]) <= threshold_lsb]
    return ok[-1] if ok else None


def marginal_r_source_is_fallback(rows: list[dict]) -> bool:
    """True when `marginal_r_source()` has no marginal case to return: no
    swept bare R_source in `rows` pushes the differential error past 1
    provisional LSB, so it falls back to the largest swept value. The
    C_decouple sweep is then run against a resistance that was NOT failing
    on its own -- that corner had nothing for decoupling to rescue, so its
    C_decouple verdict must not be counted as a rescue (issue #874). Kept
    separate from `marginal_r_source()` so the fallback is one predicate,
    asserted once, rather than re-derived at each reporting site."""
    return not any(abs(r["diff_err_lsb"]) > 1.0 for r in rows)


def marginal_r_source(rows: list[dict], r_source_list: list[float]) -> float:
    """The R_source a decoupling sweep should be run against: the smallest
    swept R_source whose bare (C_decouple = 0) differential error already
    exceeds 1 provisional LSB -- i.e. a case decoupling would actually have
    to rescue. Falls back to the largest swept R_source if no swept point
    exceeds 1 LSB (report that plainly, do not invent one). This is the
    single-corner default path's own definition, factored out so the
    --corners --sweep decouple mode can re-derive it per corner from that
    SAME corner's own bare sweep rather than borrowing the tt/27C/1.8V
    value -- the bare budget is already known to span >= an order of
    magnitude across the ratified grid
    (records/20260907-052526-f589273.md). Ask
    `marginal_r_source_is_fallback(rows)` whether the value returned is the
    fallback: a decoupling verdict measured against it is not a rescue."""
    if marginal_r_source_is_fallback(rows):
        return r_source_list[-1]
    return next(
        r for r in rows if abs(r["diff_err_lsb"]) > 1.0
    )["r_source_ohm"]


def partition_decouple_rescue(points: list[dict]) -> dict[str, list[dict]]:
    """Split `run_corners_decouple()` points for the C_decouple record's
    rescue verdict (issue #874).

    - `nothing_to_rescue`: the corner's marginal R_source is
      `marginal_r_source()`'s fallback (see
      `marginal_r_source_is_fallback()`), so its C_decouple sweep ran
      against a resistance that was not failing bare. Those corners are
      evidence of nothing either way and belong on NEITHER side of the
      verdict. Counting them as rescued is what let the record report
      "decoupling rescues N of N ratified corners" for any data.
    - `needed`: the complement -- corners whose bare R_source sweep actually
      pushed past 1 provisional LSB, the only ones a rescue claim can be
      about.
    - `rescued` / `unrescued`: of `needed`, those that do and do not have a
      1-LSB C_decouple budget (`find_budget()`, which excludes the
      C_decouple = 0 control row).

    Covered by sim/tests/test_run_vcm_drive_budget.py."""
    needed = [p for p in points if not p["marginal_is_fallback"]]
    return {
        "nothing_to_rescue": [p for p in points if p["marginal_is_fallback"]],
        "needed": needed,
        "rescued": [p for p in needed if p["budget_1lsb_f"] is not None],
        "unrescued": [p for p in needed if p["budget_1lsb_f"] is None],
    }


def single_corner_decouple_rescue_note(marginal_r_ohm: float,
                                        c_decouple_f: float) -> str:
    """The single-corner (default-path) note for a C_decouple sweep that DID
    keep the differential error within 1 provisional LSB at the marginal
    R_source (issue #882).

    `c_decouple_f` is `find_budget()`'s result on the C_decouple axis: the
    LARGEST swept value that passed. This note therefore reports it as a
    value confirmed to work, never as a floor -- the pre-#882 wording said
    "a decoupling capacitor of >= X pF ... recovers differential error",
    which asserts two things the five-point sweep did not observe: that
    every capacitance above the largest TESTED value also works, and
    (by omission) that no smaller swept value does. The record's own
    C_decouple table note already states this error is not monotonic in
    C_decouple, so "`>=`" contradicted the same record that carried it.

    Deliberately the same caveat wording as the `--corners` sibling note in
    `write_corners_decouple_record()` ("points already confirmed to work,
    not guaranteed floors -- this error is not monotonic in C_decouple"),
    which issue #874 reworded while this one was left behind.

    Pure (float in, string out) so the wording is unit-testable without
    ngspice; covered by sim/tests/test_run_vcm_drive_budget.py."""
    return (
        f"At the marginal R_source={marginal_r_ohm:.0f} ohm (worst-case "
        f"window), a decoupling capacitor of "
        f"{c_decouple_f * 1e12:.2f} pF at the on-die VCM node recovers "
        "differential error to <= 1 provisional LSB. That is the largest "
        "swept C_decouple confirmed to work here, not a guaranteed floor: "
        "smaller swept values are not implied to fail and larger "
        "(untested) values are not implied to keep working -- this error "
        "is not monotonic in C_decouple."
    )


def tt_point_seed_comparison_note(measured_budget_ohm: float | None,
                                   seed_budget_ohm: float | None,
                                   smallest_nonzero_ohm: float) -> str:
    """The full-grid record's note on its own `tt`/27C/1.8V point, COMPARED
    against the single-corner seed record's figure for the same
    window/point (issue #882).

    `measured_budget_ohm` is this grid's tt point `budget_1lsb_ohm`;
    `seed_budget_ohm` is `SINGLE_CORNER_SEED_BUDGET_1LSB_OHM[window]`.
    Either may be `None` -- "no positive bare budget", which for the seed
    is that record's own "<= 0 ohm" figure read in this script's post-#874
    convention (see `SINGLE_CORNER_SEED_BUDGET_1LSB_OHM`).

    The pre-#882 note said the tt point was "consistent with (reproduces)
    the single-corner record's own finding" whenever it had *a* budget, with
    no comparison against the seed at all -- so e.g.
    `records/20260908-100413-f3e2914.md` printed "<= 100000 ohm, consistent
    with (reproduces) ..." against a 10000 ohm seed. The sibling branch (no
    positive budget at the tt point) said nothing about the seed either way.
    This helper covers all four seed/measured cases and uses the word
    "reproduces" ONLY when the two figures agree.

    Pure (figures in, string out) so each case is unit-testable without
    ngspice; covered by sim/tests/test_run_vcm_drive_budget.py."""
    seed_ref = (f"[`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
                f"({SINGLE_CORNER_SEED_RECORD}.md)")
    if measured_budget_ohm is not None:
        measured = (
            f"The `tt`/27C/1.8V point in this grid measures a 1-LSB budget "
            f"of <= {measured_budget_ohm:.0f} ohm."
        )
    else:
        measured = (
            f"The `tt`/27C/1.8V point in this grid finds NO positive 1-LSB "
            f"budget: the smallest nonzero swept R_source "
            f"({smallest_nonzero_ohm:.0f} ohm) already exceeds 1 provisional "
            "LSB there, so that point allows zero margin for any nonzero "
            "drive impedance."
        )

    # Both sides are exact values -- a swept-list entry and a literal read
    # off the seed record -- so `==` is the right comparison, not a
    # tolerance: a tolerance would report agreement between two figures the
    # two records actually print differently.
    if measured_budget_ohm is None and seed_budget_ohm is None:
        comparison = (
            f"The single-corner seed record {seed_ref} likewise reports no "
            "positive bare budget for the same window/point, so this grid's "
            "tt point reproduces the single-corner record's own finding."
        )
    elif measured_budget_ohm is None:
        comparison = (
            f"The single-corner seed record {seed_ref} reports a "
            f"<= {seed_budget_ohm:.0f} ohm bare budget for the same "
            "window/point, so the two figures DIFFER: this grid's tt point "
            "finds no positive budget where that record found one."
        )
    elif seed_budget_ohm is None:
        comparison = (
            f"The single-corner seed record {seed_ref} reports no positive "
            "bare budget for the same window/point, so the two figures "
            "DIFFER: this grid's tt point finds a budget where that record "
            "found none."
        )
    elif measured_budget_ohm == seed_budget_ohm:
        comparison = (
            f"That is the same figure the single-corner seed record "
            f"{seed_ref} reports for the same window/point, so this grid's "
            "tt point reproduces the single-corner record's own finding."
        )
    else:
        comparison = (
            f"The single-corner seed record {seed_ref} reports "
            f"<= {seed_budget_ohm:.0f} ohm for the same window/point, so "
            f"the two figures DIFFER ({measured_budget_ohm:.0f} ohm here "
            f"vs. {seed_budget_ohm:.0f} ohm there); this grid's tt point "
            "does not reproduce the single-corner figure. Which of the two "
            "is the better reading of this point is not settled here -- "
            "both are append-only evidence from different runs."
        )
    return f"{measured} {comparison}"


# ---------------------------------------------------------------------------
# --corners execution: ONE `klt sim` request per invocation (issue #881)
# ---------------------------------------------------------------------------
# Both `--corners` legs used to loop `ngspice` in-process, one subprocess per
# (corner, swept value): 72 solves for the worst-window bare sweep, 117 for
# its decouple sibling. CLAUDE.md forbids a hand-launched grid on this shared
# dispatch host, so the four full-grid records could not be re-run at all as
# the driver stood. Each `--corners` invocation is now ONE `klt sim` request
# executed by the batch fleet, following
# sim/input-drive-budget/run_input_drive_budget.py; the single-corner default
# path below is untouched and still runs locally.
#
# WHY THE DECOUPLE LEG IS STILL ONE REQUEST. Each corner is decoupled against
# its OWN marginal R_source, which is not known until that corner's bare
# sweep has been solved -- so it cannot be written into the request. Instead
# the request carries the bare steps PLUS every (non-zero swept R_source,
# non-zero swept C_decouple) pair, and the per-corner selection happens when
# the report is decoded (`run_corners_decouple()` below). Every value
# `marginal_r_source()` can return is a non-zero swept R_source (it returns
# either the largest swept value or the first row past 1 LSB, and the control
# row's error is zero by construction), so the enumerated pairs always cover
# the corner's own marginal case. That is 8 + 7x4 = 36 steps per corner at
# the worst window and 3 + 2x4 = 11 at the legacy window, in one submit --
# and it keeps the existing property that a corner's bare and decoupled rows
# come from the same invocation. The alternative (submit the bare request,
# then one decouple request per corner) costs nine more submits and carries
# state between them, to skip solves that are cheap.


def corners_sample_end_ns(window: str) -> float:
    """End of the SAMPLE window, in ns -- `build_transient()`'s own
    expression, factored out so the ported deck's probe time and transient
    stop time are the SAME arithmetic the per-corner deck uses rather than a
    re-derivation that could drift from it."""
    sample_ns, _ = WINDOW_CONFIG[window]
    return SAMPLE_TD_NS + SAMPLE_TR_NS + sample_ns


def corners_probe_ns(window: str) -> float:
    """The fixed probe time (ns): one step-pair inside the end of the SAMPLE
    window, `build_transient()`'s own `probe_ns`."""
    return corners_sample_end_ns(window) - (TRAN_STEP_PS / 1000.0) * 2


def corners_tran_stop_ns(window: str) -> float:
    """Transient stop time (ns), `build_transient()`'s own `tran_stop_ns`."""
    return corners_sample_end_ns(window) + 50.0


def r_source_effective(r_source_ohm: float) -> float:
    """The resistance actually emitted for a swept point: `R_IDEAL_OHM`
    stands in for 0, exactly as `build_transient()` does."""
    if r_source_ohm < 0:
        raise ValueError(f"R_source must be >= 0, got {r_source_ohm!r}")
    return R_IDEAL_OHM if r_source_ohm == 0 else float(r_source_ohm)


def c_decouple_effective(c_decouple_f: float) -> float:
    """The capacitance actually emitted for a swept point: `C_IDEAL_F`
    stands in for 0 (see `C_IDEAL_F` for why the card cannot be omitted)."""
    if c_decouple_f < 0:
        raise ValueError(f"C_decouple must be >= 0, got {c_decouple_f!r}")
    return C_IDEAL_F if c_decouple_f == 0 else float(c_decouple_f)


def corners_step_name(r_source_ohm: float, c_decouple_f: float = 0.0) -> str:
    """A stable, ngspice-vector-safe step name per (R_source, C_decouple).

    The `C_decouple = 0` name is the BARE step's name on purpose: the
    decouple leg's control row IS that corner's bare row at the same
    resistance, measured in the same invocation, so the two legs share one
    solve rather than duplicating it."""
    if c_decouple_f <= 0:
        return f"bare_r{round(r_source_ohm)}"
    return f"dec_r{round(r_source_ohm)}_c{round(c_decouple_f * 1e12)}"


def build_corners_body(window: str, point: str = DEFAULT_POINT) -> str:
    """Circuit BODY for `klt sim`: no `.lib`, `.temp`, `.control` or `.end`
    (klt emits all four, and the corner axes drive the first two).

    The DUT fragment is inserted verbatim, exactly as `build_transient()`
    inserts it. Everything else is testbench, and differs from the
    per-corner deck only in the ways `DECK_PORT_CHANGES` lists: one shared
    body cannot carry a corner's supply as a literal, so `VCM` and `SAMPLE`
    are driven through supply-scaling behavioural sources, the supply source
    is named for the corner axis key, and `Cdecouple` is always present.
    `Rvcm` and `Cdecouple` are the two per-step `alter` targets."""
    vinp, vinn = TEST_POINTS[point]
    sample_ns, _ = WINDOW_CONFIG[window]
    tran_stop_ns = corners_tran_stop_ns(window)
    return "\n".join(
        [
            "* sim/vcm-drive-budget deck body -- VCM drive-impedance /",
            "* decoupling budget over the full ratified PVT grid (issue #121;",
            "* ported from a local ngspice loop to `klt sim` for issue #881).",
            "* Devices: sim/sampling-frontend/testbench/"
            "sampling_frontend_dut.spice,",
            "* read in place and inserted verbatim below.",
            f"* Test point {point} (VINP={vinp:g} V, VINN={vinn:g} V); "
            f"{window} window ({sample_ns:.3f} ns SAMPLE-high).",
            ".options num_threads=1",
            "",
            DUT_FRAGMENT.read_text().rstrip("\n"),
            "",
            f"* --- testbench sources (the supply source is named `{SUPPLY_KEY}`,",
            "* which is also the corners.supply_v axis key -- see SUPPLY_KEY) ---",
            f"{SUPPLY_KEY} VDD 0 DC {VDD_NOM}",
            f"Vinp VINP 0 dc {vinp:g}",
            f"Vinn VINN 0 dc {vinn:g}",
            "* VCM's ideal level tracks the corner's own supply through a",
            "* behavioural source, so one deck body serves every corner (the",
            f"* per-corner deck wrote the literal `dc vdd*{VCM_FRAC:g}`).",
            f"Bvcm VCM_IDEAL 0 V=v(VDD)*{VCM_FRAC:g}",
            "* The two per-step `alter` targets. Both carry their own control-row",
            "* stand-in value here (R_IDEAL_OHM / C_IDEAL_F); every step alters",
            "* both, so no step inherits another's value.",
            f"Rvcm VCM_IDEAL VCM {R_IDEAL_OHM:g}",
            f"Cdecouple VCM 0 {C_IDEAL_F:g}",
            "* SAMPLE: a normalised 0..1 pulse scaled by the corner's own supply,",
            "* so the pulse itself carries no corner-dependent voltage.",
            f"Vsmp_ctl SMP_CTL 0 pulse(0 1 {SAMPLE_TD_NS}n {SAMPLE_TR_NS}n "
            f"{SAMPLE_TR_NS}n {sample_ns}n {tran_stop_ns * 10}n)",
            "Bsample SAMPLE 0 V=v(SMP_CTL)*v(VDD)",
            "",
        ]
    )


def corners_measurement_cards(window: str) -> list[dict]:
    """The five fixed-time reads `build_transient()` emits, as `klt sim`
    measurement entries. The names are `MEASURE_NAMES`, none of which is a
    node name -- an ngspice `.meas` result is written as a vector into the
    step's own plot, so a measurement named after a node would overwrite that
    node's waveform and break every later card in the same step that reads
    it (the pitfall
    sim/input-drive-budget/run_input_drive_budget.py documents)."""
    at_ns = corners_probe_ns(window)
    return [
        {
            "name": name,
            "spice": f".meas tran {name} find v({node}) at={at_ns}n",
            "unit": "V",
        }
        for name, node in zip(
            MEASURE_NAMES, ("TOP_P", "TOP_N", "BPREF_P", "BPREF_N", "VCM")
        )
    ]


def corners_analysis_steps(window: str, sweep: str = "rsource") -> list[dict]:
    """One `tran` step per swept point, both `--sweep` legs in the one
    request shape.

    `reset: true` re-parses the circuit before each step, so a step's own
    `alter` set fully determines its deck -- no state or override leaks from
    the previous solve. klt re-emits the corner's own supply `alter` after
    the reset, so the corner axis survives it."""
    _, r_source_list = WINDOW_CONFIG[window]
    tran_args = f"{TRAN_STEP_PS}p {corners_tran_stop_ns(window)}n"
    measurements = corners_measurement_cards(window)

    def step(name: str, r_source_ohm: float, c_decouple_f: float) -> dict:
        return {
            "name": name,
            "reset": True,
            "analysis": {"kind": "tran", "args": tran_args},
            "alter": {
                "Rvcm": r_source_effective(r_source_ohm),
                "Cdecouple": c_decouple_effective(c_decouple_f),
            },
            "measurements": measurements,
        }

    steps = [step(corners_step_name(r), r, 0.0) for r in r_source_list]
    if sweep == "decouple":
        for r_source in [r for r in r_source_list if r > 0]:
            for c_decouple in [c for c in C_DECOUPLE_SWEEP_F if c > 0]:
                steps.append(
                    step(corners_step_name(r_source, c_decouple),
                         r_source, c_decouple)
                )
    return steps


def corner_ids() -> list[str]:
    """The ratified 9-point one-at-a-time PVT grid, in grid order."""
    return [
        corners_mod.corner_id(p, t, v)
        for p, t, v in corners_mod.ratified_oat_grid(
            VDD_NOM, SUPPLY_TOLERANCE, PROCESS_CORNERS, TEMPS_C
        )
    ]


def build_corners_request(
    netlist_name: str,
    cids: list[str],
    window: str,
    sweep: str = "rsource",
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    backend: str | None = None,
) -> dict:
    """The `klt sim` request for one `--corners` submission.

    The corner axes are declared as the full cross product with the points
    the one-at-a-time grid omits listed under `exclude` -- `klt sim` has no
    OAT axis form, so this is how every `--corners` campaign in this repo
    expresses the same 9-point grid."""
    pts = [corners_mod.parse_corner_id(c) for c in cids]
    procs = sorted({p for p, _, _ in pts})
    temps = sorted({t for _, t, _ in pts})
    vdds = sorted({v for _, _, v in pts})
    want = set(pts)
    exclude = [
        {"process": p, "temperature_c": t, "supply_v": {SUPPLY_KEY: v}}
        for p in procs
        for t in temps
        for v in vdds
        if (p, t, v) not in want
    ]
    req: dict = {
        "netlist": netlist_name,
        "engine": "ngspice",
        "models": {"pdk": "sky130A", "lib": "libs.tech/combined/sky130.lib.spice"},
        "corners": {
            "process": procs,
            "supply_v": {SUPPLY_KEY: vdds},
            "temperature_c": temps,
        },
        "analysis_steps": corners_analysis_steps(window, sweep),
        "options": {"timeout_s": timeout_s, "keep_artifacts": True},
    }
    if exclude:
        req["exclude"] = exclude
    if backend:
        req["backend"] = backend
    return req


def read_corners_report(report: dict) -> tuple[dict[str, dict], dict]:
    """`({corner_id: {"<step>.<name>": value}}, run info)`.

    Refuses an error ENVELOPE rather than inventing numbers, and nulls a
    corner whose own status is `error`/`inconclusive` so a partial solve is
    never read as a measurement."""
    if not isinstance(report, dict):
        raise ValueError("klt sim report is not a JSON object")
    if "error" in report and "corners" not in report:
        raise ValueError(f"klt sim error envelope: {report['error']}")
    out: dict[str, dict] = {}
    for c in report.get("corners") or []:
        sv = (c.get("supply_v") or {}).get(SUPPLY_KEY)
        cid = corners_mod.corner_id(
            c["process"], float(c["temperature_c"]), float(sv)
        )
        vals = {
            m["name"]: m.get("value")
            for m in (c.get("measurements") or [])
            if isinstance(m, dict) and "name" in m
        }
        if c.get("status") in ("error", "inconclusive"):
            vals = {k: None for k in vals}
        out[cid] = vals
    # Run-level facts come from harness.klt_sim.run_info(), which reads the
    # sharded `environment.remote.fleet[]` shape as well as the single-job
    # one -- reading only the latter is how a sharded record ends up
    # reporting `job None` (issue #865).
    return out, klt_sim.run_info(report)


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _rows_from_steps(values: dict, specs: list[tuple[str, dict]]) -> list[dict] | None:
    """Decode one corner's sweep into the row dicts the reporting helpers
    already take -- byte-for-byte the shape `run_sweep()` /
    `run_decouple_sweep()` build, so `find_budget()`,
    `marginal_r_source()`, `partition_decouple_rescue()` and both record
    writers are unchanged by the port.

    Returns None when ANY point in the sweep is missing or non-finite: a
    budget read off a partial sweep would silently be a budget over a
    different sweep list, so the corner is reported INCOMPLETE instead."""
    rows: list[dict] = []
    baseline: float | None = None
    for step, axis in specs:
        m = {name: values.get(f"{step}.{name}") for name in MEASURE_NAMES}
        if not all(_finite(v) for v in m.values()):
            return None
        diff = m["top_p_end"] - m["top_n_end"]
        row = {**axis, "diff_v": diff, **m}
        if baseline is None:
            baseline = diff
        row["diff_err_mv"] = (diff - baseline) * 1000
        row["diff_err_lsb"] = row["diff_err_mv"] / LSB_DIFF_MV_PROVISIONAL
        rows.append(row)
    return rows


def corner_bare_rows(values: dict, window: str) -> list[dict] | None:
    """One corner's bare (undecoupled) R_source sweep rows, or None when the
    sweep is incomplete."""
    _, r_source_list = WINDOW_CONFIG[window]
    return _rows_from_steps(
        values,
        [(corners_step_name(r), {"r_source_ohm": r}) for r in r_source_list],
    )


def corner_decouple_rows(values: dict, marginal_r_ohm: float) -> list[dict] | None:
    """One corner's C_decouple sweep rows at `marginal_r_ohm`, or None when
    the sweep is incomplete. The `C_decouple = 0` control row is that
    corner's own BARE step at the same resistance (see
    `corners_step_name()`)."""
    return _rows_from_steps(
        values,
        [
            (corners_step_name(marginal_r_ohm, c), {"c_decouple_f": c})
            for c in C_DECOUPLE_SWEEP_F
        ],
    )


def submit_corners(
    cids: list[str],
    workdir: Path,
    window: str,
    sweep: str = "rsource",
    *,
    point: str = DEFAULT_POINT,
    backend: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    capacity_wait_s: float | None = CAPACITY_WAIT_S,
) -> tuple[dict, dict, dict, str]:
    """Write the deck + request under `workdir`, run `klt sim`, return
    `(results, run info, request, deck body)`. An existing `report.json` is
    reused, so a re-run after a successful submit does not re-spend fleet
    capacity."""
    workdir.mkdir(parents=True, exist_ok=True)
    body = build_corners_body(window, point)
    (workdir / "tb.spice").write_text(body)
    req = build_corners_request(
        "tb.spice", cids, window, sweep, timeout_s=timeout_s, backend=backend
    )
    (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    report = klt_sim.submit(
        workdir / "request.json", workdir / "out",
        backend=backend, capacity_wait_s=capacity_wait_s,
        label=f"vcm-drive-budget {sweep}/{window}",
    )
    results, info = read_corners_report(report)
    return (
        results,
        dict(info, backend=backend or "(klt default / KLT_SIM_BACKEND)"),
        req,
        body,
    )


def _corner_point(cid: str) -> dict:
    process_corner, temp_c, supply_v = corners_mod.parse_corner_id(cid)
    return {
        "corner": process_corner, "temp_c": temp_c, "supply_v": supply_v,
        "corner_id": cid,
    }


def run_corners(results: dict, cids: list[str], window: str = "worst",
                quiet: bool = False) -> list[dict]:
    """Decode a `--sweep rsource` report into one point per ratified corner:
    the full OAT grid's bare (undecoupled) R_source budget at ONE
    acquisition window (`window`, "worst" or "legacy").

    Does NOT change the mechanism measured: identical DUT fragment,
    identical per-window R_source sweep list (`WINDOW_CONFIG[window]`),
    identical diff_err definition (referenced to that SAME corner's own
    R_source=0 point) as the single-corner default path -- only the `.lib`
    corner, `.temp`, supply voltage and the deck differences
    `DECK_PORT_CHANGES` lists vary. A corner whose sweep is missing or
    non-finite at any point is marked `complete: False` and given NO budget
    (issue #881); it is reported as INCOMPLETE rather than scored off a
    partial sweep."""
    _, r_source_list = WINDOW_CONFIG[window]
    points: list[dict] = []
    for cid in cids:
        rows = corner_bare_rows(results.get(cid) or {}, window)
        budget_1lsb = find_budget(rows, 1.0) if rows else None
        budget_p1lsb = find_budget(rows, 0.1) if rows else None
        points.append({
            **_corner_point(cid),
            "rows": rows,
            "complete": rows is not None,
            "budget_1lsb_ohm": budget_1lsb["r_source_ohm"] if budget_1lsb else None,
            "budget_1lsb_censored": bool(budget_1lsb and
                budget_1lsb["r_source_ohm"] == r_source_list[-1]),
            "budget_p1lsb_ohm": budget_p1lsb["r_source_ohm"] if budget_p1lsb else None,
        })
        if not quiet:
            p = points[-1]
            if not p["complete"]:
                print(f"{cid}: INCOMPLETE -- no usable bare sweep")
                continue
            b1 = p["budget_1lsb_ohm"]
            print(
                f"{cid}: 1-LSB R_source budget = "
                + (f"<= {b1:.0f} ohm" if b1 is not None
                   else f"< {r_source_list[1]:.0f} ohm (none found)")
            )
    return points


def run_corners_decouple(results: dict, cids: list[str], window: str = "worst",
                          quiet: bool = False) -> list[dict]:
    """Decode a `--sweep decouple` report into one point per ratified corner.

    Per corner: read that corner's own bare R_source sweep out of the same
    report, take its `marginal_r_source()`, then read the C_decouple rows
    solved against THAT resistance. Nothing about the mechanism changes:
    identical DUT fragment, identical `C_DECOUPLE_SWEEP_F` list, identical
    diff_err definition (referenced to that same corner/R_source's own
    C_decouple = 0 point) as the single-corner default path -- only the
    `.lib` corner, `.temp`, supply voltage, the per-corner marginal R_source
    and the deck differences `DECK_PORT_CHANGES` lists vary. A corner whose
    bare or C_decouple sweep is incomplete is marked `complete: False` and
    given no budget (issue #881)."""
    _, r_source_list = WINDOW_CONFIG[window]
    points: list[dict] = []
    for cid in cids:
        values = results.get(cid) or {}
        bare_rows = corner_bare_rows(values, window)
        marginal_r = (
            marginal_r_source(bare_rows, r_source_list) if bare_rows else None
        )
        rows = (
            corner_decouple_rows(values, marginal_r) if bare_rows else None
        )
        budget_1lsb = find_budget(rows, 1.0) if rows else None
        points.append({
            **_corner_point(cid),
            "rows": rows, "bare_rows": bare_rows,
            "complete": bool(bare_rows) and rows is not None,
            "marginal_r_source_ohm": marginal_r,
            # No swept bare R_source at this corner exceeded 1 LSB, so this
            # corner's C_decouple sweep ran against a resistance that was
            # not failing on its own: there was nothing to rescue, and its
            # budget must not be counted as a rescue either way (#874).
            "marginal_is_fallback": (
                marginal_r_source_is_fallback(bare_rows) if bare_rows else False
            ),
            "budget_1lsb_f": budget_1lsb["c_decouple_f"] if budget_1lsb else None,
            "budget_1lsb_censored": bool(budget_1lsb and
                budget_1lsb["c_decouple_f"] == C_DECOUPLE_SWEEP_F[-1]),
        })
        if not quiet:
            p = points[-1]
            if not p["complete"]:
                print(f"{cid}: INCOMPLETE -- no usable sweep")
                continue
            b1 = p["budget_1lsb_f"]
            print(
                f"{cid}: marginal R_source = {p['marginal_r_source_ohm']:.0f} ohm"
                + (" (fallback -- no swept R_source exceeded 1 LSB bare, "
                   "nothing to rescue)" if p["marginal_is_fallback"] else "")
                + ", 1-LSB C_decouple budget = "
                + (f"<= {b1 * 1e12:.2f} pF" if b1 is not None
                   else "none found in the swept range")
            )
    return points


# ---------------------------------------------------------------------------
# --corners record sections shared by both writers (issue #881)
# ---------------------------------------------------------------------------
def split_complete(points: list[dict]) -> tuple[list[dict], list[dict]]:
    """`(complete, incomplete)`. A point with no `complete` key predates the
    `klt sim` port's INCOMPLETE handling and is treated as complete, so a
    caller that builds points by hand (the unit tests) is unaffected."""
    complete = [p for p in points if p.get("complete", True)]
    return complete, [p for p in points if not p.get("complete", True)]


def incomplete_note(points: list[dict]) -> str | None:
    """The Result bullet naming corners that produced no usable sweep.

    An incomplete corner is NOT a corner with no budget: `find_budget()`
    returning None is a measurement ("the smallest nonzero swept value
    already exceeds the tier"), while an incomplete corner was never
    measured at all. Reporting one as the other is exactly the confusion
    this bullet exists to prevent (issue #881), so incomplete corners are
    excluded from every count below it and named here instead."""
    complete, incomplete = split_complete(points)
    if not incomplete:
        return None
    label = ", ".join(f"`{p['corner_id']}`" for p in incomplete)
    return (
        f"**INCOMPLETE at {len(incomplete)} of {len(points)} ratified "
        f"corners** ({label}): at least one swept point there is missing or "
        "non-finite in the `klt sim` report, so no budget is stated for "
        "those corners and they are excluded from every count in this "
        "section. A budget read off a partial sweep would be a budget over a "
        "different sweep list, not a measurement. Every figure below is over "
        f"the {len(complete)} corner(s) that completed."
    )


def write_corners_artifacts(record_id: str, artifacts: dict[str, str] | None) -> None:
    """Commit the `klt sim` request, the deck body and the raw report beside
    the record, under `corners/<record-id>/` -- the layout
    sim/input-drive-budget/ already uses, so the exact request that produced
    a record can be re-submitted without reconstructing it from the runner."""
    if not artifacts:
        return
    base = EXPERIMENT_DIR / "corners" / record_id
    (base / "request").mkdir(parents=True, exist_ok=True)
    for name in ("request.json", "tb.spice"):
        if artifacts.get(name) is not None:
            (base / "request" / name).write_text(artifacts[name])
    if artifacts.get("report.json") is not None:
        (base / "report.json").write_text(artifacts["report.json"])


def klt_client_version() -> str:
    """`klt --version`, or a stated placeholder when the client is absent."""
    try:
        done = subprocess.run(
            ["klt", "--version"], capture_output=True, text=True, check=False
        )
    except OSError:
        return "(klt --version unavailable)"
    return done.stdout.strip() or "(klt --version unavailable)"


def executing_environment(prov, info: dict | None) -> dict:
    """What actually produced the numbers: the executing fleet worker when it
    reported itself, otherwise the SUBMITTING host -- stated as such, never
    silently substituted."""
    info = info or {}
    worker_pdk = info.get("worker_pdk")
    worker_ngspice = info.get("worker_ngspice")
    known = bool(worker_pdk and worker_ngspice)
    jobs = info.get("jobs") or []
    runner_klt = next(
        (j.get("runner_klt_version") for j in jobs if j.get("runner_klt_version")),
        None,
    )
    return {
        "known": known,
        "pdk": worker_pdk if known else prov.pdk_line,
        "ngspice": worker_ngspice if known else prov.ng_version,
        "runner_klt": runner_klt,
    }


def corners_klt_run_lines(prov, info: dict | None, sweep: str, window: str,
                          record_id: str) -> list[str]:
    """The `klt sim` run block and the uncontrolled-difference statements
    every `--corners` record carries since the port (issue #881).

    Three differences are stated, because all three are uncontrolled between
    a record minted here and the record it supersedes: the PDK commit, the
    simulator version, and the execution route -- plus every deck change the
    port itself made (`DECK_PORT_CHANGES`). None of them is a correction to
    the older record; they are the reasons a figure may differ without the
    circuit having changed."""
    info = info or {}
    env = executing_environment(prov, info)
    prev = predecessor_environment(sweep, window)
    exec_matches_host = (
        env["known"]
        and str(prov.pdk_line).split("@")[-1].strip()
           == str(env["pdk"]).split("@")[-1].strip()
        and str(prov.ng_version).strip() == str(env["ngspice"]).strip()
    )
    jobs = info.get("jobs") or []

    lines = [
        "## `klt sim` run",
        "",
        f"- job `{info.get('job_id')}`, status `{info.get('status')}`, backend "
        f"`{info.get('backend')}`, executing PDK `{info.get('worker_pdk')}`, "
        f"executing simulator `{info.get('worker_ngspice')}`"
        + (f", sharded over {len(jobs)} job(s)" if info.get("sharded") else ""),
    ]
    for job in jobs:
        lines.append(
            f"- job `{job.get('job_id')}`: state `{job.get('state')}`, exit "
            f"`{job.get('exit_code')}`, instance `{job.get('instance_type')}`, "
            f"elapsed {job.get('elapsed_seconds')} s, runner klt "
            f"`{job.get('runner_klt_version')}`"
        )
    lines += [
        f"- request and deck body: `corners/{record_id}/request/`; raw report: "
        f"`corners/{record_id}/report.json`",
        "",
        "## Uncontrolled differences against the record this supersedes",
        "",
    ]

    prev_ref = f"[`records/{prev['record']}.md`]({prev['record']}.md)"
    if prev["pdk"] and prev["ngspice"]:
        same_pdk = str(prev["pdk"]).split("@")[-1].strip() == str(env["pdk"]).split("@")[-1].strip()
        same_ng = str(prev["ngspice"]).strip() == str(env["ngspice"]).strip()
        lines.append(
            f"- **PDK commit and simulator version.** {prev_ref} was minted on "
            f"`{prev['pdk']}` / `{prev['ngspice']}` (read from that record's own "
            f"Environment block); this record was produced on `{env['pdk']}` / "
            f"`{env['ngspice']}`. "
            + (
                "Those are the same, so neither is an uncontrolled difference "
                "between the two runs."
                if (same_pdk and same_ng)
                else "**Those differ.** Any change in a figure between the two "
                "records is as readily a PDK or simulator-version difference as "
                "a circuit or harness one; nothing here is a controlled "
                "comparison against that record, and no figure in it is "
                "corrected by this one."
            )
        )
    else:
        lines.append(
            f"- **PDK commit and simulator version.** {prev_ref}'s own "
            "Environment block could not be read from this tree, so the "
            "comparison is not stated rather than guessed. This record was "
            f"produced on `{env['pdk']}` / `{env['ngspice']}`."
        )
    lines += [
        "- **Execution route.** The superseded record's grid was solved by an "
        "in-process `ngspice` loop on the submitting host, one subprocess per "
        "(corner, swept value). This record's grid is ONE `klt sim` request "
        "executed by the batch fleet (block above), one unit per corner, with "
        "each swept value an `analysis_steps[]` entry inside that unit. The "
        "numbers therefore come from a different machine, a different "
        "scheduler and a different deck-assembly path than the record it "
        "supersedes.",
        "- **Submitting host vs. executing worker.** The Environment block "
        "below names the PDK and ngspice of the EXECUTING worker when it "
        "reported them"
        + (
            f"; the submitting host resolved `{prov.pdk_line}` / "
            f"`{prov.ng_version}`. "
            + (
                "They are the same for this run."
                if exec_matches_host
                else "**They differ for this run**, so no figure here is "
                "controlled for PDK or simulator version against a locally run "
                "record."
            )
            if env["known"]
            else ". The worker did NOT report them for this run, so the block "
            "below names the SUBMITTING host's instead, and no figure here is "
            "attributable to a known executing environment."
        ),
    ]
    lines += [
        "- **Deck changes made by the port itself** (issue #881) -- each is a "
        "consequence of one shared deck body with the corner applied as an "
        "axis, not a change of mechanism:",
    ]
    lines += [f"  - {text}" for text in DECK_PORT_CHANGES]
    lines.append("")
    return lines


def corners_environment_lines(prov, info: dict | None) -> list[str]:
    """`evidence.environment_block()` for a `--corners` record: the EXECUTING
    worker's PDK and simulator, with the submitting host's own stated beside
    them, plus the klt client and runner versions."""
    env = executing_environment(prov, info)
    return evidence.environment_block(
        env["pdk"],
        env["ngspice"],
        prov.netlist_sha,
        extra={
            "klt (client)": klt_client_version(),
            "klt (fleet runner)": env["runner_klt"] or "(not reported)",
            "PDK / ngspice above": "as run by the executing worker"
            if env["known"]
            else "submitting host (executing worker did not report)",
            "submitting host PDK / ngspice": f"{prov.pdk_line} / {prov.ng_version}",
            "tran step": f"{TRAN_STEP_PS:g} ps",
            "toolchain pin file": "sim/toolchain.json",
        },
    )


def write_corners_decouple_record(points: list[dict], point: str,
                                   window: str = "worst",
                                   supersedes: str = "",
                                   *,
                                   info: dict | None = None,
                                   artifacts: dict[str, str] | None = None) -> Path:
    """Evidence record for `run_corners_decouple()` -- same provenance /
    scope / no-ratified-claim conventions as `write_corners_record()`, with
    the C_decouple axis in place of the R_source axis.

    `info` is `harness.klt_sim.run_info()`'s view of the submission that
    produced `points`, and `artifacts` the request/deck/report texts to
    commit beside the record (issue #881)."""
    supersedes = supersedes or default_corners_supersedes("decouple", window)
    netlist_text = DUT_FRAGMENT.read_text()
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    record_id = prov.record_id
    record_path = prov.record_path
    write_corners_artifacts(record_id, artifacts)
    complete, _incomplete = split_complete(points)

    process_corners_run = sorted({p["corner"] for p in points})
    temps_run = sorted({p["temp_c"] for p in points})
    supplies_run = sorted({p["supply_v"] for p in points})
    sample_ns, r_source_list = WINDOW_CONFIG[window]
    window_desc = WINDOW_DESCRIPTION[window]
    other_window = "legacy" if window == "worst" else "worst"
    other_window_desc = WINDOW_DESCRIPTION[other_window]

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance budget -- full PVT grid -- {window} window -- "
      f"C_decouple sweep -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) `C_decouple` "
        f"sweep in [`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- at the {window_desc} "
        "acquisition window only -- to the FULL ratified PVT corner set "
        "(spec/target-spec.md's \"Numeric rows -- RATIFIED 2026-08-19\" "
        "section), the same OAT grid this mechanism's own bare R_source "
        "campaigns and every other "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 "
        "mechanism campaign already sweep. Identical DUT fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "unmodified), identical `C_DECOUPLE_SWEEP_F` list, identical "
        "diff_err definition (referenced to that same corner/R_source's own "
        "C_decouple = 0 point) as the single-corner record. **Unlike the "
        "bare R_source full-grid campaigns, each corner here is decoupled "
        "against its OWN marginal R_source** (`marginal_r_source()`, "
        "re-derived from that same corner's own bare sweep in the same "
        "invocation) rather than a value borrowed from tt/27C/1.8V -- the "
        "bare budget is already known to span >= an order of magnitude "
        "across this grid ([`records/20260907-052526-f589273.md`]"
        "(20260907-052526-f589273.md)), so a single borrowed resistance "
        "would not be the marginal case at most corners. No claim here is "
        "graded against a ratified spec row: `spec/target-spec.md` is "
        "entirely DRAFT (#1/#27); `LSB_DIFF_MV_PROVISIONAL` is a reference "
        "scale, never a pass/fail gate; the DR-006 acquisition window is "
        "itself downstream of the DRAFT sample-rate row (Section 7 Item 2)."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "read in place -- not duplicated, same convention as the "
        "single-corner record. This record's own harness adds only the "
        "ideal-source/R_source/C_decouple network into `VCM` and the SAMPLE "
        "pulse source, with `.lib`/`.temp`/vdd varying per corner point; "
        "neither is stated in the DUT fragment itself."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        f"- **Scope**: only the `{point}` test point's C_decouple sweep at "
        f"the {window_desc} window ({sample_ns:.3f} ns) is reported per "
        f"corner, over the "
        f"`[{', '.join(f'{c * 1e12:g}' for c in C_DECOUPLE_SWEEP_F)}]` pF "
        "sweep list, each "
        "corner at its own marginal R_source (see the table below). The "
        f"{other_window_desc} window's own C_decouple sweep stays "
        "single-corner-only (tt/27C/1.8V), deferred to a future pass -- the "
        "same one-window-per-pass precedent this mechanism's own bare "
        "R_source full-grid work already established."
    )
    a("")
    a("## C_decouple budget for <= 1 provisional LSB of differential error, per corner")
    a("")
    a(
        "\"Budget\" is the LAST (largest, in ascending sweep order) swept "
        "NONZERO C_decouple for which `abs(diff_err_lsb) <= 1.0` still holds "
        "at that corner's own marginal R_source -- see `find_budget()` in "
        "this script, the same convention the bare R_source full-grid "
        "records already use, applied to the C_decouple axis here. The "
        "C_decouple = 0 control row is excluded: it is the row every other "
        "row's error is measured against, so its own error is identically "
        "zero and reporting it would state a \"budget\" of 0 pF for a sweep "
        "in which no capacitor actually worked. It is **not** "
        "necessarily the smallest sufficient C_decouple, and larger values "
        "are not guaranteed to also work: the single-corner seed record's "
        "own C_decouple sweep already found this error is **not** monotonic "
        "in C_decouple (a bigger cap lengthens the same node's settling "
        "time constant as much as it stiffens its DC impedance). A budget "
        f"equal to the largest swept value "
        f"({C_DECOUPLE_SWEEP_F[-1] * 1e12:.0f} pF) is right-censored. "
        "\"None found\" means no swept nonzero C_decouple value, at that "
        "corner's own marginal R_source, keeps the error within 1 LSB -- "
        "decoupling alone does not rescue that corner within the swept "
        "range. A marginal R_source marked **(fallback)** is NOT a marginal "
        "case: no swept bare R_source at that corner exceeded 1 provisional "
        "LSB, so `marginal_r_source()` fell back to the largest swept value "
        "and the C_decouple sweep there was run against a resistance that "
        "was not failing on its own. Those corners had nothing for "
        "decoupling to rescue, and their budget column is reported but not "
        "counted as a rescue in the Result section below."
    )
    a("")
    a("| Corner | Marginal R_source (ohm) | 1-LSB C_decouple budget (pF) |")
    a("|---|---|---|")
    for p in points:
        if not p.get("complete", True):
            a(f"| `{p['corner_id']}` | (incomplete) | (incomplete) |")
            continue
        b1 = p["budget_1lsb_f"]
        b1_str = "none found" if b1 is None else (
            f"<= {b1 * 1e12:.2f}"
            + (" (right-censored)" if p["budget_1lsb_censored"] else "")
        )
        r_str = f"{p['marginal_r_source_ohm']:.0f}" + (
            " (fallback)" if p["marginal_is_fallback"] else ""
        )
        a(f"| `{p['corner_id']}` | {r_str} | {b1_str} |")
    a("")

    a("## Per-corner C_decouple sweeps")
    a("")
    a(
        "Full swept data behind the budget table above -- `diff_err` is "
        "referenced to that same corner/R_source's own C_decouple = 0 row, "
        "so it isolates exactly the contribution of the decoupling "
        "capacitor at that corner."
    )
    a("")
    a("| Corner | R_source (ohm) | C_decouple (pF) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
    a("|---|---|---|---|---|---|")
    for p in complete:
        for r in p["rows"]:
            a(
                f"| `{p['corner_id']}` | {p['marginal_r_source_ohm']:.0f} | "
                f"{r['c_decouple_f'] * 1e12:.2f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
    a("")

    # A corner whose marginal R_source is the fallback had no bare failure
    # to rescue, so its C_decouple budget is neither a rescue nor a failed
    # one -- it is excluded from BOTH sides of the verdict rather than
    # padding the "N of N rescued" count (#874).
    split = partition_decouple_rescue(complete)
    nothing_to_rescue = split["nothing_to_rescue"]
    needed = split["needed"]
    rescued = split["rescued"]
    unrescued = split["unrescued"]
    notes: list[str] = []
    missing = incomplete_note(points)
    if missing:
        notes.append(missing)
    if nothing_to_rescue:
        nothing_label = ", ".join(
            f"`{p['corner_id']}`" for p in nothing_to_rescue
        )
        notes.append(
            f"**{len(nothing_to_rescue)} of {len(complete)} ratified corners "
            f"had nothing for decoupling to rescue** ({nothing_label}): no "
            f"swept bare R_source at those corners pushed the differential "
            f"error past 1 provisional LSB, so `marginal_r_source()` fell "
            f"back to the largest swept value "
            f"({r_source_list[-1]:.0f} ohm) and the C_decouple sweep there "
            "measured a resistance that was not failing on its own. Whatever "
            "their budget column says, those corners are **not** evidence "
            "that decoupling rescues anything, and they are excluded from "
            "the rescue counts below."
        )
    if rescued:
        largest = max(p["budget_1lsb_f"] for p in rescued)
        smallest = min(p["budget_1lsb_f"] for p in rescued)
        largest_label = ", ".join(
            f"`{p['corner_id']}`" for p in rescued if p["budget_1lsb_f"] == largest
        )
        smallest_label = ", ".join(
            f"`{p['corner_id']}`" for p in rescued if p["budget_1lsb_f"] == smallest
        )
        notes.append(
            f"**Decoupling keeps the change in differential error within 1 "
            f"provisional LSB of that corner's own undecoupled point at "
            f"{len(rescued)} of the {len(needed)} ratified corner(s) whose "
            f"bare R_source sweep actually failed**, each at that corner's "
            f"own marginal R_source. Among those, the largest working value "
            f"found is {largest * 1e12:.2f} pF ({largest_label}) and the "
            f"smallest is {smallest * 1e12:.2f} pF ({smallest_label}). Per "
            "the table note above these are points already confirmed to "
            "work, not guaranteed floors -- this error is not monotonic in "
            "C_decouple."
        )
    if unrescued:
        unrescued_label = ", ".join(f"`{p['corner_id']}`" for p in unrescued)
        notes.append(
            f"**{len(unrescued)} of the {len(needed)} ratified corner(s) "
            "whose bare R_source sweep actually failed are NOT rescued by "
            "any swept nonzero C_decouple** at their own marginal R_source "
            f"({unrescued_label}): at those corners the real drive path "
            "needs a lower source resistance, not just more capacitance."
        )
    elif needed:
        notes.append(
            f"None of the {len(needed)} ratified corner(s) whose bare "
            "R_source sweep actually failed was left unrescued within the "
            "swept C_decouple range -- but see the non-monotonicity caveat "
            "above before reading any of these as a floor."
        )
    else:
        notes.append(
            "**No ratified corner's bare R_source sweep failed at all**, so "
            "this campaign establishes nothing about whether decoupling "
            "rescues this mechanism: every corner's C_decouple sweep ran "
            "against a fallback resistance that was already inside 1 "
            "provisional LSB undecoupled. A C_decouple campaign that can "
            "answer the rescue question needs a bare sweep that reaches a "
            "failing R_source at each corner first."
        )
    notes.append(
        "The per-corner marginal R_source values in the table above are "
        "themselves re-derived from each corner's own bare sweep in this "
        "same invocation, and reproduce the bare R_source full-grid "
        "campaign's own per-corner shape "
        "([`records/20260907-052526-f589273.md`]"
        "(20260907-052526-f589273.md)) rather than assuming the "
        "tt/27C/1.8V value applies everywhere."
    )
    notes.append(
        f"This campaign repeats ONLY the C_decouple sweep at the "
        f"{window_desc} window. The {other_window_desc} window's own "
        "C_decouple sweep remains single-corner (tt/27C/1.8V) only; a "
        "full-grid pass over it is a natural next step, the same "
        "one-window-per-pass precedent this mechanism's own bare R_source "
        "full-grid campaigns already established. It does not, on its own, "
        "establish what R_source/C_decouple an actual on-chip VCM buffer or "
        "off-chip reference network would present -- no such buffer exists "
        "in this design yet (docs/chipalooza/challenge-4-proposal.md "
        "Section 2.2)."
    )

    a("## Result")
    a("")
    for n in notes:
        a(f"- {n}")
    a("")

    a("## Reproduction")
    a("")
    window_flag = "" if window == "worst" else f" --window {window}"
    a(
        "```bash\n# One-time machine bootstrap: docs/environment-setup.md "
        "sections 1-3.\nsource sim/env.sh\npython3 "
        "sim/vcm-drive-budget/run_vcm_drive_budget.py --corners"
        f"{window_flag} --sweep decouple --record\n```"
    )
    a("")
    a(
        "The grid is ONE `klt sim` request submitted to the batch fleet with "
        f"`--wait-for-capacity {CAPACITY_WAIT_S:g}`; no `ngspice` loop runs on "
        "the submitting host (CLAUDE.md's host rule). `--probe` runs a single "
        "corner at a single swept point locally and is the only path that "
        "does."
    )
    a("")
    lines += corners_klt_run_lines(prov, info, "decouple", window, record_id)
    lines += corners_environment_lines(prov, info)
    lines += evidence.footer_lines(
        written_by=WRITTEN_BY,
        supersedes=supersedes,
    )
    evidence.close_record(prov, lines, "Record")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
    return record_path


def write_corners_record(points: list[dict], point: str,
                          window: str = "worst",
                          supersedes: str = "",
                          *,
                          info: dict | None = None,
                          artifacts: dict[str, str] | None = None) -> Path:
    """Evidence record for `run_corners()`.

    `info` is `harness.klt_sim.run_info()`'s view of the submission that
    produced `points`, and `artifacts` the request/deck/report texts to
    commit beside the record (issue #881)."""
    supersedes = supersedes or default_corners_supersedes("rsource", window)
    netlist_text = DUT_FRAGMENT.read_text()
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    record_id = prov.record_id
    record_path = prov.record_path
    write_corners_artifacts(record_id, artifacts)
    complete, _incomplete = split_complete(points)

    process_corners_run = sorted({p["corner"] for p in points})
    temps_run = sorted({p["temp_c"] for p in points})
    supplies_run = sorted({p["supply_v"] for p in points})
    sample_ns, r_source_list = WINDOW_CONFIG[window]
    window_desc = WINDOW_DESCRIPTION[window]
    other_window = "legacy" if window == "worst" else "worst"
    other_window_desc = WINDOW_DESCRIPTION[other_window]

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance budget -- full PVT grid -- {window} window -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: extends the single-corner (tt/27C/1.8V) bare "
        f"(undecoupled) R_source budget in [`records/{SINGLE_CORNER_SEED_RECORD}.md`]"
        f"({SINGLE_CORNER_SEED_RECORD}.md) -- at the {window_desc} "
        "acquisition window only -- to the "
        "FULL ratified PVT corner set (spec/target-spec.md's \"Numeric "
        "rows -- RATIFIED 2026-08-19\" section), the same OAT grid every "
        "other `docs/chipalooza/challenge-4-proposal.md` Section 7 Item 2 "
        "mechanism campaign now sweeps. Identical DUT fragment "
        "(`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "unmodified), identical R_source sweep list, identical diff_err "
        "definition (referenced to that same corner's own R_source=0 "
        "point) as the single-corner record -- only the `.lib` corner, "
        "`.temp`, and supply voltage vary per point. No claim here is "
        "graded against a ratified spec row: `spec/target-spec.md` is "
        "entirely DRAFT (#1/#27); `LSB_DIFF_MV_PROVISIONAL` is a reference "
        "scale, never a pass/fail gate; the DR-006 acquisition window is "
        "itself downstream of the DRAFT sample-rate row (Section 7 Item 2)."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice`, "
        "read in place -- not duplicated, same convention as the "
        "single-corner record. This record's own harness adds only the "
        "ideal-source/R_source network into `VCM` and the SAMPLE pulse "
        "source, with `.lib`/`.temp`/vdd varying per corner point; neither "
        "is stated in the DUT fragment itself."
    )
    a(
        corners_mod.corner_matrix_summary_line(
            process_corners_run, temps_run, supplies_run, len(points)
        )
    )
    a(
        f"- **Scope, narrower than the single-corner default run**: only "
        f"the `{point}` test point's bare (undecoupled) R_source sweep at "
        f"the {window_desc} window ({sample_ns:.3f} ns) is repeated "
        f"per corner, over the reduced `{r_source_list}` sweep list. The "
        f"{other_window_desc} window and the C_decouple sweep stay "
        "single-corner-only (tt/27C/1.8V), deferred to a future pass, "
        "same first-pass/full-grid split precedent the other mechanism "
        "campaigns already established."
    )
    a("")
    a("## Bare R_source budget for <= 1 provisional LSB of differential error, per corner")
    a("")
    a(
        "\"Budget\" is the largest swept NONZERO R_source (ohm) at which "
        "`abs(diff_err_lsb) <= 1.0` still holds at that corner -- see "
        f"`find_budget()` in this script. The R_source = 0 control row is "
        "excluded: it is the row every other row's error is measured "
        "against, so its own error is identically zero and reporting it "
        "would state a \"budget\" of 0 ohm for a sweep in which no source "
        "resistance actually worked. \"none (< smallest nonzero tested)\" "
        f"means the smallest nonzero swept value ({r_source_list[1]:.0f} "
        "ohm) already exceeds the tier -- that corner allows **zero** "
        "margin for any nonzero drive impedance, which is a TIGHTER result "
        "than any number in this column, not a missing measurement. A "
        f"budget equal to the largest swept value "
        f"({r_source_list[-1]:.0f} ohm) is right-censored: every "
        "swept value stayed under threshold, so the true budget is >= that "
        "value, not necessarily equal to it."
    )
    a("")
    a("| Corner | 1-LSB R_source budget (ohm) | 0.1-LSB R_source budget (ohm) |")
    a("|---|---|---|")
    for p in points:
        if not p.get("complete", True):
            a(f"| `{p['corner_id']}` | (incomplete) | (incomplete) |")
            continue
        b1 = p["budget_1lsb_ohm"]
        b1_str = "none (< smallest nonzero tested)" if b1 is None else (
            f"<= {b1:.0f}" + (" (right-censored)" if p["budget_1lsb_censored"] else "")
        )
        bp1 = p["budget_p1lsb_ohm"]
        bp1_str = "none (< smallest nonzero tested)" if bp1 is None else f"<= {bp1:.0f}"
        a(f"| `{p['corner_id']}` | {b1_str} | {bp1_str} |")
    a("")

    scored = [p for p in complete if p["budget_1lsb_ohm"] is not None]
    # `find_budget()` excludes the R_source = 0 control row (#874), so a
    # None budget here means "the smallest nonzero swept R_source already
    # exceeds the tier" -- a corner STRICTLY TIGHTER than any scored one,
    # not an unmeasured one. It must stay in the binding-corner reasoning
    # rather than being filtered out the way a missing value would be.
    none_found = [p for p in complete if p["budget_1lsb_ohm"] is None]
    smallest_nonzero = r_source_list[1]
    none_label = ", ".join(f"`{p['corner_id']}`" for p in none_found)
    notes: list[str] = []
    missing = incomplete_note(points)
    if missing:
        notes.append(missing)
    binding_val: float | None = None
    binding_label = ""
    if none_found:
        notes.append(
            f"**Binding corner(s) (no positive 1-LSB budget at all): "
            f"{none_label}** -- at {len(none_found)} of {len(complete)} "
            f"ratified corners the smallest nonzero swept R_source "
            f"({smallest_nonzero:.0f} ohm) already exceeds 1 provisional "
            "LSB of differential error. Those corners allow **zero** margin "
            "for any nonzero drive impedance"
            + ("; nothing in the budget column above is tighter than they "
               "are." if scored else ", and no corner in this grid has a "
               "positive 1-LSB budget at all.")
        )
    if scored:
        # Every scored budget is a nonzero swept R_source (find_budget()
        # excludes the zero control row), so the spread ratio below cannot
        # divide by zero.
        binding_val = min(p["budget_1lsb_ohm"] for p in scored)
        best_val = max(p["budget_1lsb_ohm"] for p in scored)
        binding_ties = [p for p in scored if p["budget_1lsb_ohm"] == binding_val]
        best_ties = [p for p in scored if p["budget_1lsb_ohm"] == best_val]
        binding = binding_ties[0]
        best = best_ties[0]
        binding_label = (
            f"`{binding['corner_id']}`" if len(binding_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in binding_ties)
        )
        best_label = (
            f"`{best['corner_id']}`" if len(best_ties) == 1
            else "tied at " + ", ".join(f"`{p['corner_id']}`" for p in best_ties)
        )
        spread_phrase = (
            "Worst-to-best spread "
            + ("among the corner(s) that have one" if none_found
               else "across the ratified grid")
            + f": {best_val / binding_val:.1f}x -- the bare R_source budget "
            "is **not** corner-invariant."
        )
        lead = (
            f"Among the {len(scored)} ratified corner(s) that DO have a "
            f"positive 1-LSB budget, the tightest is {binding_label}, "
            f"<= {binding_val:.0f} ohm."
            if none_found else
            f"**Binding corner(s) (tightest 1-LSB budget): "
            f"{binding_label}**, <= {binding_val:.0f} ohm."
        )
        notes.append(
            lead
            + f" Loosest corner(s): {best_label}, <= {best_val:.0f} ohm"
            + (" (right-censored)" if best["budget_1lsb_censored"] else "")
            + f". {spread_phrase}"
        )
    # No `else`: `scored` can only be empty when `none_found` is every point,
    # which the note above already states -- a second "no corner found a
    # budget" line would only restate it.

    tt_pt = next(
        (p for p in complete if p["corner"] == "tt" and p["temp_c"] == 27.0
         and p["supply_v"] == VDD_NOM), None,
    )
    # `seed_budget is None` is the seed record's own "<= 0 ohm" figure read
    # in this script's post-#874 convention -- see
    # SINGLE_CORNER_SEED_BUDGET_1LSB_OHM.
    seed_budget = SINGLE_CORNER_SEED_BUDGET_1LSB_OHM[window]

    if tt_pt is not None:
        # Compared against the seed figure, not asserted against it (#882).
        notes.append(
            tt_point_seed_comparison_note(
                tt_pt["budget_1lsb_ohm"], seed_budget, smallest_nonzero
            )
        )

    if seed_budget is not None and none_found:
        notes.append(
            f"**This tightens, not merely restates, the single-corner "
            f"finding**: the single-corner (tt/27C/1.8V) record reports a "
            f"<= {seed_budget:.0f} ohm bare budget at this window, but "
            f"{len(none_found)} of {len(complete)} ratified corners "
            f"({none_label}) have no positive budget at all -- the smallest "
            f"nonzero swept R_source ({smallest_nonzero:.0f} ohm) already "
            "exceeds 1 provisional LSB there. Any future on-chip VCM buffer "
            "/ off-chip reference network sizing that targets only the "
            "tt/27C/1.8V figure would under-budget the real worst-case "
            "corner."
        )
    elif (seed_budget is not None and binding_val is not None
            and binding_val < seed_budget):
        notes.append(
            f"**This tightens, not merely restates, the single-corner "
            f"finding**: the single-corner (tt/27C/1.8V) record reports "
            f"a <= {seed_budget:.0f} ohm bare budget at this window, but "
            f"the binding corner(s) across the ratified grid "
            f"({binding_label}) is/are <= {binding_val:.0f} ohm -- "
            f"{seed_budget / binding_val:.1f}x tighter. Any "
            "future on-chip VCM buffer / off-chip reference network "
            "sizing that targets only the tt/27C/1.8V figure would "
            "under-budget the real worst-case corner."
        )
    elif seed_budget is None and complete and len(none_found) == len(complete):
        notes.append(
            "**This confirms, at every ratified corner, the "
            "single-corner record's already-tightest finding**: the "
            "single-corner (tt/27C/1.8V) record already reports no "
            "positive bare budget at this window (the R_source=0 "
            "ideal-source control is the only point inside 1 provisional "
            "LSB -- the smallest nonzero R_source tested already exceeds "
            f"it), and every one of the {len(complete)} ratified "
            "corners reproduces that same floor. This window offers "
            "**zero** margin for any nonzero drive impedance, at any "
            "ratified corner -- consistent with the single-corner "
            "record's own finding that the legacy window is the MORE "
            "demanding case for this mechanism, not merely restating "
            "it at one point."
        )
    elif seed_budget is None and none_found and scored:
        # Mixed grid: `scored` non-empty, so best_* below are bound.
        best_raw_label = ", ".join(f"`{p['corner_id']}`" for p in best_ties)
        notes.append(
            "**This reveals the single-corner (tt/27C/1.8V) no-positive-"
            "budget finding is itself corner-dependent, not a uniform "
            f"floor**: {len(none_found)} of {len(complete)} ratified "
            f"corners ({none_label}) reproduce that same floor (zero "
            "margin for any nonzero drive impedance at those corners), "
            f"but the remaining {len(scored)} corner(s) recover a "
            f"positive budget, up to <= {best_val:.0f} ohm"
            + (" (right-censored)" if best["budget_1lsb_censored"] else "")
            + f" at {best_raw_label}. Any future on-chip VCM buffer / "
            "off-chip reference network sizing must still budget for "
            "the zero-margin corner(s) above, not the tt/27C/1.8V "
            "point alone -- the single-corner record's own scope "
            "note (single point, not yet corner-complete) was "
            "correct to flag this as unresolved."
        )
    elif seed_budget is None:
        notes.append(
            "**This loosens the single-corner (tt/27C/1.8V) finding**: that "
            "record reports no positive bare budget at this window, yet "
            f"every one of the {len(complete)} ratified corners in this grid "
            "recovers one. Treat the discrepancy as unresolved -- the two "
            "runs are not otherwise controlled against each other -- rather "
            "than as a relaxation of the single-corner bound."
        )
    notes.append(
        f"This campaign repeats ONLY the bare (undecoupled) R_source sweep "
        f"at the {window_desc} window, at every ratified corner. The "
        f"{other_window_desc} window and the C_decouple sweep remain "
        "single-corner (tt/27C/1.8V) only; a full-grid pass "
        "over either is a natural next step, same open-item shape as the "
        "other Section 7 Item 2 mechanisms before their own full-grid "
        "passes landed. It does not, on its own, establish what R_source/"
        "C_decouple an actual on-chip VCM buffer or off-chip reference "
        "network would present -- no such buffer exists in this design "
        "yet (docs/chipalooza/challenge-4-proposal.md Section 2.2)."
    )

    a("## Result")
    a("")
    for n in notes:
        a(f"- {n}")
    a("")

    a("## Reproduction")
    a("")
    window_flag = "" if window == "worst" else f" --window {window}"
    a(
        "```bash\n# One-time machine bootstrap: docs/environment-setup.md "
        "sections 1-3.\nsource sim/env.sh\npython3 "
        "sim/vcm-drive-budget/run_vcm_drive_budget.py --corners"
        f"{window_flag} --record\n```"
    )
    a("")
    a(
        "The grid is ONE `klt sim` request submitted to the batch fleet with "
        f"`--wait-for-capacity {CAPACITY_WAIT_S:g}`; no `ngspice` loop runs on "
        "the submitting host (CLAUDE.md's host rule). `--probe` runs a single "
        "corner at a single swept point locally and is the only path that "
        "does."
    )
    a("")
    lines += corners_klt_run_lines(prov, info, "rsource", window, record_id)
    lines += corners_environment_lines(prov, info)
    lines += evidence.footer_lines(
        written_by=WRITTEN_BY,
        supersedes=supersedes,
    )
    evidence.close_record(prov, lines, "Record")
    evidence.write_latest_pointer(EXPERIMENT_DIR, record_id)
    return record_path


def write_record(all_results: dict, supersedes: str = "") -> None:
    supersedes = supersedes or SINGLE_CORNER_SUPERSEDES_DEFAULT
    netlist_text = DUT_FRAGMENT.read_text()
    prov = evidence.resolve_provenance(EXPERIMENT_DIR, netlist_text)
    record_id = prov.record_id
    netlist_sha = prov.netlist_sha
    pdk_line = prov.pdk_line
    ng_version = prov.ng_version

    lines: list[str] = []
    a = lines.append
    a(f"# VCM drive-impedance / decoupling budget -- {record_id}")
    a("")
    a("- **Record ID**: " + record_id)
    a(
        "- **Claim**: quantifies, for the first time in this repo, how the "
        "sampling front end's SAMPLE-window sampled value "
        "(`design/sampling_frontend.sch`, TOP_P/TOP_N) degrades as a "
        "function of a non-ideal `VCM` drive resistance (`R_source`, in "
        "series with an otherwise-ideal reference into the shared on-die "
        "`VCM` net that both differential legs' `Cmswn/Cmswp` switches tie "
        "to) and how much on-die decoupling capacitance at `VCM` relaxes "
        "that bound -- answering "
        "`docs/chipalooza/challenge-4-proposal.md` Section 7 Item 5 (every "
        "existing testbench drives `VCM` ideally; no drive-impedance/"
        "decoupling budget existed). No claim against a ratified spec row: "
        "`spec/target-spec.md` is entirely DRAFT (#1/#27); the DR-006 "
        "acquisition-window figures used here are themselves downstream of "
        "the DRAFT sample-rate row (Section 7 Item 2); "
        "`LSB_DIFF_MV_PROVISIONAL` is quoted only as a reference scale, "
        "never a pass/fail gate, matching "
        "`sim/sampling-frontend/run_hold_kick.py`'s own convention."
    )
    a(
        "- **Netlist provenance**: unmodified "
        "`sim/sampling-frontend/testbench/sampling_frontend_dut.spice` "
        "(design/sampling_frontend.sch regenerated fragment, issue #52), "
        "read in place -- not duplicated. This record's own harness adds "
        "only the ideal-source/R_source/C_decouple network into `VCM` and "
        "the SAMPLE pulse source; both are stated directly in this record's "
        "own `run_vcm_drive_budget.py`, not in the DUT fragment itself."
    )
    a(
        "- **Point/corner matrix**: `tt`/27C/1.8V only, at "
        f"`{DEFAULT_POINT}` (and `common_mode` for the decoupling-sweep "
        "cross-check) -- a mechanism-isolating, single-corner budget "
        "derivation, the same precedent "
        "`sim/sampling-frontend/run_hold_kick.py` Experiments 1-5 already "
        "established for this sub-block. Full PVT-corner coverage of this "
        "budget (switch R_on varies materially with process/temperature) "
        "is deferred to a future full corner campaign, same open item as "
        "#28 for the rest of this sub-block's characterization."
    )
    a(
        "- **Acquisition windows tested**: "
        f"{T_SAMPLE_WORST_NS:.3f} ns (DR-006-derived worst case, "
        "f_clk=12 MHz -- shortest, least forgiving), "
        f"{T_SAMPLE_LEGACY_NS:.1f} ns (this repo's pre-existing "
        "`run_transient.py`/`run_hold_kick.py` testbench convention, "
        "independent of DR-006, kept for direct comparison -- these two "
        "had never previously been reconciled)."
    )
    a("")

    for window_label, sample_ns, rows, _r_list in all_results["sweeps"]:
        a(f"## R_source sweep -- {window_label} window "
          f"({sample_ns:.3f} ns SAMPLE-high)")
        a("")
        a(
            "Differential TOP_P-TOP_N sampled value at the end of the SAMPLE "
            "window, referenced to this same sweep's own R_source=0 (ideal-"
            "source) point -- i.e. `diff_err` isolates exactly the "
            "contribution of R_source, not the front end's pre-existing "
            "in-sample settling error (already characterized ideally in "
            "`sim/sampling-frontend/records/`)."
        )
        a("")
        a("| R_source (ohm) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
        a("|---|---|---|---|")
        for r in rows:
            a(
                f"| {r['r_source_ohm']:.0f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
        a("")

    for window_label, sample_ns, r_source_ohm, rows in all_results["decouple_sweeps"]:
        a(
            f"## C_decouple sweep -- {window_label} window "
            f"({sample_ns:.3f} ns SAMPLE-high), R_source={r_source_ohm:.0f} ohm"
        )
        a("")
        a("| C_decouple (pF) | VCM(end) (V) | diff_err (mV) | diff_err (LSB, informational) |")
        a("|---|---|---|---|")
        for r in rows:
            a(
                f"| {r['c_decouple_f'] * 1e12:.2f} | {r['vcm_end']:.5f} | "
                f"{r['diff_err_mv']:+.4f} | {r['diff_err_lsb']:+.4f} |"
            )
        a("")

    a("## Result")
    a("")
    for note in all_results["notes"]:
        a(f"- {note}")
    a("")

    a("## Reproduction")
    a("")
    a(
        "```\npython3 sim/vcm-drive-budget/run_vcm_drive_budget.py --record\n```"
    )
    a("")
    lines += evidence.environment_block(
        pdk_line, ng_version, netlist_sha,
        extra={"toolchain pin file": "sim/toolchain.json"},
    )
    lines += evidence.footer_lines(
        written_by=WRITTEN_BY,
        supersedes=supersedes,
    )
    evidence.close_record(prov, lines, "Record")


def corners_dry_run(args) -> int:
    """`--dry-run`: write the deck and request and print the unit and step
    counts, without submitting anything."""
    cids = corner_ids()
    workdir = args.workdir or Path(
        tempfile.mkdtemp(prefix="sim-vcm-drive-budget-dryrun-")
    )
    workdir.mkdir(parents=True, exist_ok=True)
    body = build_corners_body(args.window, args.point)
    (workdir / "tb.spice").write_text(body)
    req = build_corners_request(
        "tb.spice", cids, args.window, args.sweep, timeout_s=args.timeout_s
    )
    (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    steps = req["analysis_steps"]
    bare = sum(1 for st in steps if st["name"].startswith("bare_"))
    print(f"wrote deck + request under {workdir}")
    print(f"sweep: {args.sweep}  window: {args.window}  point: {args.point}")
    print(f"corners: {len(cids)}  units: {len(cids)}  "
          f"steps/corner: {len(steps)} ({bare} bare + "
          f"{len(steps) - bare} decoupled)")
    print(f"total solves: {len(cids) * len(steps)}  "
          f"per-unit timeout_s: {args.timeout_s:g}  "
          f"conservative whole-job bound: "
          f"{args.timeout_s * len(cids) + 120:g} s")
    return 0


def corners_probe(args, scratch: Path) -> int:
    """`--probe`: the single-unit deck-port control required before the grid
    is submitted (issue #881).

    One corner (tt/27C/1.8V), one non-zero swept R_source, run BOTH ways on
    THIS host against THIS PDK: the ported `--corners` deck through `klt sim
    --backend local`, and the per-corner `build_transient()` deck through
    one `ngspice`. Printing the difference in `top_p_end - top_n_end`
    separates the deck port from the PDK and simulator change a re-run also
    carries -- a grid run on the fleet cannot, because both move at once.
    Mints no record and changes no evidence."""
    cid = corners_mod.corner_id("tt", 27.0, VDD_NOM)
    r_source = args.probe_r_source
    if r_source <= 0:
        print("--probe-r-source must be > 0: the port's deck differences "
              "are what this compares, and the R_source = 0 control row "
              "exercises neither alter target at a swept value",
              file=sys.stderr)
        return 2
    sample_ns, _ = WINDOW_CONFIG[args.window]
    workdir = args.workdir or Path(
        tempfile.mkdtemp(prefix="sim-vcm-drive-budget-probe-")
    )

    # Side A: the ported deck, through klt sim, locally.
    workdir.mkdir(parents=True, exist_ok=True)
    body = build_corners_body(args.window, args.point)
    (workdir / "tb.spice").write_text(body)
    req = build_corners_request(
        "tb.spice", [cid], args.window, "rsource",
        timeout_s=args.timeout_s, backend="local",
    )
    req["analysis_steps"] = [
        st for st in req["analysis_steps"]
        if st["name"] == corners_step_name(r_source)
    ]
    if not req["analysis_steps"]:
        print(f"--probe-r-source {r_source:g} is not in the {args.window} "
              f"window's sweep list {WINDOW_CONFIG[args.window][1]}",
              file=sys.stderr)
        return 2
    (workdir / "request.json").write_text(json.dumps(req, indent=1) + "\n")
    report = klt_sim.submit(workdir / "request.json", workdir / "out",
                            backend="local", capacity_wait_s=None,
                            label="vcm-drive-budget probe")
    results, info = read_corners_report(report)
    ported = {
        name: (results.get(cid) or {}).get(
            f"{corners_step_name(r_source)}.{name}")
        for name in MEASURE_NAMES
    }
    if not all(_finite(v) for v in ported.values()):
        print(f"{cid}: INCOMPLETE -- the ported deck produced no usable "
              f"measurement ({ported})", file=sys.stderr)
        return 1

    # Side B: the per-corner deck this path used before the port, through
    # one local ngspice -- the same _run() the single-corner default path
    # uses, at a single point (CLAUDE.md permits a single local unit).
    vinp, vinn = TEST_POINTS[args.point]
    local = _run(
        build_transient(vinp=vinp, vinn=vinn, sample_width_ns=sample_ns,
                        r_source_ohm=r_source, corner="tt", temp_c=27.0,
                        vdd=VDD_NOM),
        scratch, f"probe_{args.window}_{args.point}_{r_source:g}",
    )

    diff_ported = ported["top_p_end"] - ported["top_n_end"]
    diff_local = local["top_p_end"] - local["top_n_end"]
    delta_mv = (diff_ported - diff_local) * 1e3
    print(f"{cid}  window={args.window} ({sample_ns:.3f} ns)  "
          f"R_source={r_source:g} ohm  point={args.point}")
    print(f"  ported deck (klt sim --backend local): "
          f"top_p_end - top_n_end = {diff_ported:.9f} V")
    print(f"  build_transient() deck (ngspice):      "
          f"top_p_end - top_n_end = {diff_local:.9f} V")
    print(f"  difference: {delta_mv:+.6f} mV "
          f"({delta_mv / LSB_DIFF_MV_PROVISIONAL:+.6f} provisional LSB)")
    for name in MEASURE_NAMES:
        print(f"    {name:11} ported {ported[name]:+.9f} V   "
              f"local {local[name]:+.9f} V   "
              f"delta {(ported[name] - local[name]) * 1e3:+.6f} mV")
    print(f"  klt sim: backend {info.get('resolved_backend')}, "
          f"status {info.get('status')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true",
                    help="write an evidence record under records/")
    ap.add_argument("--point", default=DEFAULT_POINT, choices=list(TEST_POINTS),
                    help="primary differential test point for the R_source sweep")
    ap.add_argument(
        "--corners", action="store_true",
        help="run the full ratified PVT grid (9 OAT points) instead of the "
             "single-corner (tt/27C/1.8V) default -- bare R_source sweep at "
             "one acquisition window only, selected by --window (see module "
             "docstring)",
    )
    ap.add_argument(
        "--window", default="worst", choices=list(WINDOW_CONFIG),
        help="acquisition window swept by --corners: 'worst' (DR-006 "
             "worst-case, 12 MHz, default) or 'legacy' (this repo's "
             "pre-existing 400 ns testbench convention). Ignored without "
             "--corners.",
    )
    ap.add_argument(
        "--sweep", default="rsource", choices=["rsource", "decouple"],
        help="which leg of the budget --corners repeats per corner: "
             "'rsource' (bare undecoupled R_source sweep, default) or "
             "'decouple' (C_decouple sweep, each corner at its own marginal "
             "R_source). Ignored without --corners.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="write the --corners deck + request to --workdir, print the "
             "corner and step counts, and stop (no simulation, no submit)",
    )
    ap.add_argument(
        "--probe", action="store_true",
        help="ONE corner (tt/27C/1.8V) at ONE non-zero R_source "
             "(--probe-r-source), run BOTH ways locally -- the ported "
             "--corners deck through `klt sim --backend local` and the "
             "per-corner build_transient() deck through ngspice -- and "
             "print the difference in top_p_end - top_n_end. The single-unit "
             "deck-port control; the only local simulation on the --corners "
             "side, and it changes no record.",
    )
    ap.add_argument(
        "--probe-r-source", type=float, default=10e3,
        help="the non-zero swept R_source --probe compares at "
             "(default: %(default)s ohm)",
    )
    ap.add_argument(
        "--backend", default=None,
        help="klt sim backend for --corners (default: klt's own / "
             "KLT_SIM_BACKEND, which on a dispatch host is the batch fleet). "
             "The multi-corner grid is never looped locally.",
    )
    ap.add_argument(
        "--workdir", type=Path, default=None,
        help="where --corners writes its deck, request and report "
             "(default: a fresh temporary directory). An existing "
             "report.json there is REUSED rather than re-simulated, so a "
             "resumed run does not re-spend fleet capacity.",
    )
    ap.add_argument(
        "--timeout-s", type=float, default=DEFAULT_TIMEOUT_S,
        help="per-unit options.timeout_s for --corners (default: "
             "%(default)s). The fleet refuses a job whose timeout_s * units "
             "+ 120 exceeds its whole-job ceiling -- see DEFAULT_TIMEOUT_S "
             "before raising this",
    )
    evidence.add_supersedes_argument(
        ap,
        extra_help=(
            "Omitting it here does NOT write `(none)`: each of this runner's "
            "three write paths falls back to the fixed historical narrative "
            "naming the pre-issue-#236 record that path displaced once (the "
            "single-corner default path: "
            f"{SINGLE_CORNER_SEED_RECORD}; --corners: whichever of "
            "CORNERS_SUPERSEDES_RECORD matches --sweep/--window). A re-run "
            "that displaces a different record MUST pass this flag -- see "
            "issue #513."
        ),
    )
    args = ap.parse_args()

    scratch = Path("/tmp") / "sim-vcm-drive-budget"
    scratch.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        return corners_dry_run(args)

    if args.probe:
        return corners_probe(args, scratch)

    if args.corners:
        sample_ns, _ = WINDOW_CONFIG[args.window]
        cids = corner_ids()
        workdir = args.workdir or Path(
            tempfile.mkdtemp(prefix="sim-vcm-drive-budget-corners-")
        )
        print(f"=== VCM drive-budget: full ratified PVT grid "
              f"({args.sweep} sweep, {args.window} {sample_ns:.3f} ns "
              f"window only) ===")
        results, info, req, body = submit_corners(
            cids, workdir, args.window, args.sweep, point=args.point,
            backend=args.backend, timeout_s=args.timeout_s,
        )
        artifacts = {
            "request.json": (workdir / "request.json").read_text(),
            "tb.spice": body,
            "report.json": (workdir / "report.json").read_text(),
        }
        if args.sweep == "decouple":
            points = run_corners_decouple(results, cids, window=args.window)
            if args.record:
                write_corners_decouple_record(points, args.point,
                                              window=args.window,
                                              supersedes=args.supersedes,
                                              info=info, artifacts=artifacts)
            return 0
        points = run_corners(results, cids, window=args.window)
        if args.record:
            write_corners_record(points, args.point, window=args.window,
                                 supersedes=args.supersedes,
                                 info=info, artifacts=artifacts)
        return 0

    sweeps = []
    print("=== R_source sweep: DR-006 worst-case window "
          f"({T_SAMPLE_WORST_NS:.3f} ns) ===")
    worst_rows = run_sweep(args.point, T_SAMPLE_WORST_NS, "worst", scratch)
    sweeps.append(("worst-case (12 MHz)", T_SAMPLE_WORST_NS, worst_rows,
                   R_SOURCE_SWEEP_OHM))

    print("\n=== R_source sweep: legacy testbench window "
          f"({T_SAMPLE_LEGACY_NS:.1f} ns) ===")
    legacy_rows = run_sweep(args.point, T_SAMPLE_LEGACY_NS, "legacy", scratch,
                            r_source_list=R_SOURCE_SWEEP_LEGACY_OHM)
    sweeps.append(("legacy (400 ns)", T_SAMPLE_LEGACY_NS, legacy_rows,
                   R_SOURCE_SWEEP_LEGACY_OHM))

    # Pick a representative "marginal" R_source for the decoupling sweep --
    # see marginal_r_source()'s own docstring for the definition (shared
    # with the --corners --sweep decouple path, which re-derives it per
    # corner).
    marginal_r = marginal_r_source(worst_rows, R_SOURCE_SWEEP_OHM)
    marginal_is_fallback = marginal_r_source_is_fallback(worst_rows)

    print(f"\n=== C_decouple sweep at R_source={marginal_r:.0f} ohm, "
          f"worst-case window ===")
    decouple_rows = run_decouple_sweep(
        args.point, T_SAMPLE_WORST_NS, "worst", marginal_r, scratch
    )
    decouple_sweeps = [("worst-case (12 MHz)", T_SAMPLE_WORST_NS, marginal_r,
                        decouple_rows)]

    notes = []
    for label, sample_ns, rows, r_list in sweeps:
        budget_1lsb = find_budget(rows, 1.0)
        budget_p1lsb = find_budget(rows, 0.1)
        if budget_1lsb is None:
            notes.append(
                f"{label} window: even the smallest tested nonzero "
                f"R_source ({r_list[1]:.0f} ohm) already "
                "exceeds 1 provisional LSB of differential error -- no "
                "positive R_source budget found within the swept range at "
                "this window without decoupling."
            )
        else:
            note = (
                f"{label} window: bare (undecoupled) R_source budget is "
                f"<= {budget_1lsb['r_source_ohm']:.0f} ohm for <= 1 "
                "provisional LSB of differential error"
            )
            if budget_1lsb["r_source_ohm"] == r_list[-1]:
                note += " (right-censored -- every swept value stayed under 1 LSB, true budget is >= this)"
            if budget_p1lsb is not None:
                note += (
                    f"; <= {budget_p1lsb['r_source_ohm']:.0f} ohm for "
                    "<= 0.1 LSB"
                )
            notes.append(note + ".")

    dec_budget_1lsb = find_budget(decouple_rows, 1.0)
    if marginal_is_fallback:
        # `marginal_r` is marginal_r_source()'s documented fallback, not a
        # marginal case: nothing in the bare sweep failed, so this sweep
        # cannot be read as a decoupling rescue either way (#874).
        found = (
            f"the largest swept C_decouple keeping the change in "
            f"differential error within 1 provisional LSB of the "
            f"undecoupled point is "
            f"{dec_budget_1lsb['c_decouple_f'] * 1e12:.2f} pF"
            if dec_budget_1lsb is not None else
            "no swept nonzero C_decouple kept the change in differential "
            "error within 1 provisional LSB of the undecoupled point"
        )
        notes.append(
            f"No swept bare R_source up to the largest tested "
            f"({marginal_r:.0f} ohm) pushed the differential error past 1 "
            "provisional LSB at the worst-case window, so the C_decouple "
            "sweep ran against a resistance that was not failing on its own "
            "(`marginal_r_source()`'s documented fallback, not a marginal "
            f"case). On that sweep, {found}. That is **not** evidence that "
            "decoupling rescues this mechanism -- at this R_source there "
            "was nothing to rescue."
        )
    elif dec_budget_1lsb is not None:
        notes.append(
            single_corner_decouple_rescue_note(
                marginal_r, dec_budget_1lsb["c_decouple_f"]
            )
        )
    else:
        notes.append(
            f"At the marginal R_source={marginal_r:.0f} ohm (worst-case "
            "window), no decoupling capacitor up to the largest tested "
            f"({C_DECOUPLE_SWEEP_F[-1] * 1e12:.0f} pF) recovered "
            "differential error to within 1 provisional LSB -- decoupling "
            "alone is not a fix at this R_source; the real drive path "
            "needs a lower source resistance, not just more capacitance "
            "(consistent with an RC-charging picture: within a fixed, "
            "short acquisition window, a bigger C_decouple lengthens the "
            "same node's own settling time constant as much as it "
            "stiffens its DC impedance)."
        )
    notes.append(
        "This is a first-pass, single-corner (tt/27C/1.8V) budget, not a "
        "fabrication-ready spec: it does not yet establish what R_source "
        "and C_decouple an actual on-chip VCM buffer or off-chip reference "
        "network would present (no such buffer exists in this design yet, "
        "per docs/chipalooza/challenge-4-proposal.md Section 2.2 -- every "
        "existing block-level testbench in sim/ still drives VCM from an "
        "ideal source). What this record newly establishes is the target "
        "those (not-yet-designed) blocks would need to meet."
    )

    print()
    for n in notes:
        print(f"- {n}")

    if args.record:
        write_record(
            {
                "sweeps": sweeps,
                "decouple_sweeps": decouple_sweeps,
                "notes": notes,
            },
            supersedes=args.supersedes,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

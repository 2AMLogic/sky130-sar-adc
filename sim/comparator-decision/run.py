#!/usr/bin/env python3
"""Standalone driver for the comparator-decision experiment (issue #54).

Exercises design/comparator.sch's dynamic (StrongARM-class) latched
comparator core -- via the xschem-generated device fragment
sim/comparator-decision/testbench/comparator_core.spice -- for its decision
behavior in isolation: offset, input-referred noise, and regeneration time
vs. differential input. No sampling front end, CDAC array, or SAR logic is
required; every source here is an ideal differential DC/pulse stimulus.

    python3 sim/comparator-decision/run.py --check-env
    python3 sim/comparator-decision/run.py regen --record
    python3 sim/comparator-decision/run.py regen-corners --record
        # full ratified PVT corner sweep of the decision-delay measurement
        # (issue #121 -- the comparator half of the bit-trial timing budget
        # docs/chipalooza/challenge-4-proposal.md Section 7 Item 2 names)
    python3 sim/comparator-decision/run.py offset --record --n 16 --seed 1
    python3 sim/comparator-decision/run.py offset-bisect --record
        # decision-boundary bisection over Vindiff (issue #515): separates a
        # SYSTEMATIC decision offset (the Vindiff where resolved polarity
        # turns over) from a genuine NON-DECISION / dead band (a Vindiff
        # range resolving on neither polarity), which the single linearized
        # pick-off number of `offset` above conflates into one figure. Runs
        # tt/27C (the symmetry negative control) and ss/-40C (slow/cold) by
        # default; --points picks others. Mismatch-free by construction, so
        # it measures the systematic term only -- the random/mismatch sigma
        # stays `offset`'s job. Consumed by
        # spec/decision-records/DR-020-comparator-offset-and-dead-band-spec-rows.md
    python3 sim/comparator-decision/run.py noise --record
    python3 sim/comparator-decision/run.py noise-corners --record
        # full ratified PVT corner sweep of the noise measurement (issue #28)
    python3 sim/comparator-decision/run.py kickback --record
        # single-corner (tt/27C) kickback probe: 1kOhm series source
        # impedance into VINP/VINN, measuring the peak pin disturbance
        # across the CLK reset->evaluate transition (issue #346), plus its
        # common-mode / differential decomposition and later recovery
        # pick-offs (issue #390, DR-014's first gate) -- informational:
        # spec/target-spec.md's Kickback row is DRAFT (DR-011 via #361) and
        # spec/README.md forbids grading against a DRAFT value
    python3 sim/comparator-decision/run.py kickback-neutralized --record
        # identical probe, against the EXPERIMENTAL cross-coupled-
        # neutralization DUT variant (testbench/comparator_core_neutralized.
        # spice) instead of the adopted design -- issue #434, DR-014
        # Consequences Sec.4 / Open items' headroom-neutral mitigation-class
        # follow-on. Also informational; does not touch design/comparator.sch

Why this is a bespoke driver, not sim/run_corners.py or sim/monte_carlo.py:
those two runners are deliberately built around a single ngspice analysis
type -- a plain `.op` operating point, with measurements taken via a
`.control ... op ... let/print ... .endc` block (see
sim/harness/testbench.py's `_render_body()` and sim/harness/measure.py's
docstring on why `.measure op` itself is not usable at all). A dynamic
latched comparator has no static DC operating point during regeneration --
it is a clocked, bistable circuit -- so "offset" and "regeneration time"
are inherently transient-analysis quantities, and "input-referred noise"
needs an AC `.noise` analysis on a linearized sub-model (see the `noise`
subcommand below). Reusing the op-only runners here would silently produce
meaningless single-point snapshots rather than a clear failure, so this
experiment gets its own driver instead -- see sim/README.md's directory
convention, which this driver still follows (testbench/, netlist-snapshots/,
corners/, mc-draws/, records/), and sim/harness/{pdk,toolchain,evidence}.py,
which it reuses directly for PDK resolution, the ngspice invocation +
timeout, and the evidence-record scaffolding (record IDs, netlist SHA-256,
git/environment block) -- so records from this experiment are directly
comparable in format to every other record under sim/.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from comparator_campaigns.common import (
    DUT_CHOICES,
    DUT_FRAGMENT_NEUTRALIZED,
    NOISE_BUDGET_BASELINE_V,
)
from comparator_campaigns.kickback import (
    run_kickback_sweep,
    write_kickback_evidence,
)
from comparator_campaigns.kickback_neutralized import (
    write_kickback_neutralized_evidence,
)
from comparator_campaigns.noise import (
    run_noise,
    run_noise_corners,
    write_noise_campaign_evidence,
    write_noise_evidence,
)
from comparator_campaigns.offset_bisect import (
    BISECT_DEFAULT_POINTS,
    run_offset_bisect_points,
)
from comparator_campaigns.offset_bisect_evidence import (
    write_offset_bisect_evidence,
)
from comparator_campaigns.offset_bisect_mc import (
    bisect_mc_stats,
    bisect_negctrl_status,
    run_offset_bisect_mc,
    write_offset_bisect_mc_evidence,
)
from comparator_campaigns.pickoff_offset import (
    run_offset_mc,
    write_offset_evidence,
)
from comparator_campaigns.regen import (
    run_regen_sweep,
    write_regen_evidence,
)
from comparator_campaigns.regen_corners import (
    run_regen_corners,
    write_regen_corners_evidence,
)
from harness import toolchain

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="comparator-decision standalone testbench driver (issue #54)")
    ap.add_argument(
        "mode", nargs="?",
        choices=[
            "regen", "regen-corners", "offset", "offset-bisect", "offset-bisect-mc", "noise",
            "noise-corners", "kickback", "kickback-neutralized",
        ],
        help="which characterization to run",
    )
    ap.add_argument("--check-env", action="store_true", help="check toolchain + PDK, print summary, exit")
    ap.add_argument("--corner", default="tt")
    ap.add_argument("--temp", type=float, default=27.0)
    ap.add_argument(
        "--points", default="",
        help=(
            "offset-bisect: comma-separated <process-corner>:<temp_c> PVT "
            "points to measure, e.g. 'tt:27,ss:-40'. Default is "
            + ",".join(f"{c}:{t:g}" for c, t in BISECT_DEFAULT_POINTS)
            + " (issue #515's two acceptance-criteria points). Ignored by "
            "every other mode, which take --corner/--temp."
        ),
    )
    ap.add_argument(
        "--dut", choices=sorted(DUT_CHOICES), default="schematic",
        help=(
            "offset-bisect / offset-bisect-mc: which DUT fragment to run -- 'schematic' (default, "
            "xschem-derived comparator_core.spice) or 'extracted' (the "
            "comparator sub-block's klt pex post-layout netlist, issue #525). "
            "Ignored by every other mode."
        ),
    )
    ap.add_argument("--seed", type=int, default=1, help="offset: MC base seed")
    ap.add_argument("--n", type=int, default=16, help="offset/offset-bisect-mc: MC sample count")
    ap.add_argument(
        "--negctrl-n", type=int, default=None,
        help="offset-bisect-mc: negative-control draws (default: --n)",
    )
    ap.add_argument("--record", action="store_true", help="write an evidence record under records/")
    ap.add_argument("--note", default="")
    ap.add_argument(
        "--supersedes", default="",
        help=(
            "prior <record-id> this run REPLACES for the same claim (e.g. a "
            "re-characterization after a topology change). Written into the "
            "record's **Supersedes** field, which sim/report/generate.py "
            "--check reads to detect a manifest still citing the superseded "
            "record. Omit for a record making a different claim."
        ),
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.check_env:
        result = toolchain.check_env()
        print(toolchain.summary())
        for w in result.warnings:
            print(f"  ! warning: {w}")
        for m in result.messages:
            print(f"  - {m}")
        return result.status

    if not args.mode:
        ap.print_help()
        return 2

    if args.mode == "regen":
        points = run_regen_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_regen_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        unresolved = [p for p in points if p.regen_time_ns is None]
        return 0 if not unresolved else 1

    if args.mode == "regen-corners":
        points = run_regen_corners(quiet=args.quiet)
        if args.record:
            path = write_regen_corners_evidence(
                points, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        problems = [p for p in points if p.classify() not in ("DECIDED", "CONTROL-OK")]
        for p in problems:
            print(f"{p.classify()}: {p.corner_id} at vindiff={p.vindiff_mv:+.4f}mV")
        if problems:
            print(
                f"\n{len(problems)}/{len(points)} points did not yield a valid "
                "decision-delay measurement. This is a reported finding, not a "
                "harness error -- see the record's 'What this means' section."
            )
        return 0 if not problems else 1

    if args.mode == "offset":
        result = run_offset_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n, quiet=args.quiet
        )
        if args.record:
            path = write_offset_evidence(
                result, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        negctrl_stdev = statistics.pstdev(result.negctrl_offset_v) if len(result.negctrl_offset_v) > 1 else 0.0
        draws_stdev = statistics.pstdev(result.draws_offset_v) if len(result.draws_offset_v) > 1 else 0.0
        return 0 if (negctrl_stdev == 0.0 and draws_stdev > 0) else 1

    if args.mode == "offset-bisect-mc":
        res = run_offset_bisect_mc(
            corner=args.corner, temp_c=args.temp, seed=args.seed, n=args.n,
            negctrl_n=args.negctrl_n, quiet=args.quiet,
            dut_fragment=DUT_CHOICES[args.dut],
        )
        if args.record:
            path = write_offset_bisect_mc_evidence(
                res, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        st = bisect_mc_stats(res.draws)
        ctl = bisect_negctrl_status(res.negctrl)
        ok = ctl == "PASS"
        print(f"{st}; negative control {ctl}")
        return 0 if (ok and st["n_bounded"] > 1) else 1

    if args.mode == "offset-bisect":
        points = None
        if args.points:
            points = []
            for spec in args.points.split(","):
                spec = spec.strip()
                if not spec:
                    continue
                if ":" not in spec:
                    print(
                        f"--points entry {spec!r} is not <process-corner>:<temp_c>",
                        file=sys.stderr,
                    )
                    return 2
                process_corner, temp_str = spec.split(":", 1)
                points.append((process_corner.strip(), float(temp_str)))
        dut_fragment = DUT_CHOICES[args.dut]
        results = run_offset_bisect_points(
            points=points, quiet=args.quiet, dut_fragment=dut_fragment,
        )
        if args.record:
            path = write_offset_bisect_evidence(
                results, note=args.note, supersedes=args.supersedes,
                dut_fragment=dut_fragment,
            )
            print(f"wrote {path}")
        for r in results:
            if r.bounded:
                print(
                    f"{r.corner_id}: systematic offset "
                    f"{r.offset_mv:+.4f} +-{r.offset_unc_mv:.4f} mV, dead band "
                    f"{r.dead_band_mv:.4f} +-{r.dead_band_unc_mv:.4f} mV "
                    f"({'RESOLVED' if r.dead_band_resolved else 'below floor'})"
                )
            else:
                print(f"{r.corner_id}: {r.status} -- no boundary pair extracted")
                for n in r.notes:
                    print(f"  - {n}")
        # Informational only, same as `kickback`: spec/target-spec.md has no
        # offset or dead-band row (DRAFT or ratified) to grade against, so the
        # exit status reports whether the MEASUREMENT completed, never a
        # verdict on the circuit.
        return 0 if all(r.bounded for r in results) else 1

    if args.mode == "noise":
        result = run_noise(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_noise_evidence(
                result, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        return 0

    if args.mode == "noise-corners":
        results = run_noise_corners(quiet=args.quiet)
        if args.record:
            path = write_noise_campaign_evidence(
                results, note=args.note, supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        binding = max(results, key=lambda r: r.differential_rms_v)
        return 0 if binding.differential_rms_v <= NOISE_BUDGET_BASELINE_V else 1

    if args.mode == "kickback":
        points = run_kickback_sweep(corner=args.corner, temp_c=args.temp, quiet=args.quiet)
        if args.record:
            path = write_kickback_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        # Informational only (no ratified/DRAFT spec/target-spec.md Kickback
        # row to grade against -- see write_kickback_evidence()'s Claim
        # field) -- always succeeds if the sweep itself completed.
        return 0

    if args.mode == "kickback-neutralized":
        points = run_kickback_sweep(
            corner=args.corner, temp_c=args.temp, quiet=args.quiet,
            dut_fragment=DUT_FRAGMENT_NEUTRALIZED,
        )
        if args.record:
            path = write_kickback_neutralized_evidence(
                points, args.corner, args.temp, note=args.note,
                supersedes=args.supersedes,
            )
            print(f"wrote {path}")
        # Informational only, same as `kickback` -- see
        # write_kickback_neutralized_evidence()'s Claim field.
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

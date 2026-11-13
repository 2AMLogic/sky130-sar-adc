#!/usr/bin/env python3
"""Summary plots of this repository's simulation evidence (issue #835).

    python3 sim/report/plots.py --list     # what is plotted, and from what
    python3 sim/report/plots.py --check    # staleness gate (CI); stdlib only
    python3 sim/report/plots.py --render   # (re)write docs/plots/*.svg + manifest.json

## Why this module exists

The published Chipalooza brief (`rules-4.html`, quoted in issue #835) asks
that "simulation results should be summarized in plots, not raw data", while
also requiring that the raw data stay reproducible from the repository. This
repository over-met the second half and did not meet the first at all: every
result is an append-only Markdown record with its per-corner raw artifacts
committed beside it (`sim/README.md` "Append-only rule"), and before this
module `git ls-files` matched no image file anywhere in the tree.

This module adds the summary half *without* touching the evidence half. It
renders a small set of reader-facing figures from files that are **already
committed** -- it runs no simulation, opens no network socket, and needs no
display. Every number a figure shows was measured by a run that already
minted a record; this module only draws it.

## The three decisions this module settles (`sim/README.md` "Summary plots")

1. **Location: `docs/plots/`, regenerable, outside every evidence gate.**
   A plot is a *derived view* of evidence, not evidence itself: it is
   overwritten on regeneration and is never cited by
   `signoff/block-manifest.json`. `sim/check_append_only.py` protects
   `sim/<experiment>/records/*.md` plus the `corners`, `mc-draws`,
   `netlist-snapshots`, `diagnostics`, `runs` and `yield-reports` artifact
   directories; `docs/plots/` is outside that set (that script's own docstring
   names `docs/characterization-report.md` as similarly outside), so a
   re-render can never churn an evidence hash. No plot is ever written inside
   a `records/` tree.
2. **Format: SVG**, written head-less (matplotlib's SVG backend, no display)
   by this committed script. SVG is reviewable text rather than an opaque
   binary diff, and `svg.fonttype = "none"` keeps the labels as greppable
   text instead of glyph outlines.
3. **Gate: input-hash staleness, stdlib only.** `--render` records, per plot,
   the SHA-256 of every committed file it read, of this script itself, and of
   the SVG it wrote, into `docs/plots/manifest.json`. `--check` re-hashes
   those and fails on any mismatch, on a committed SVG with no manifest entry,
   and on a manifest entry with no file. It imports no matplotlib, so it runs
   inside `npm run check:ci` as-is (reached from `sim/report/generate.py
   --check`) on a checkout with no rendering dependency installed.

   `--check` deliberately does **not** re-render and compare bytes. SVG output
   is not expected to be stable across matplotlib and font versions, so a
   byte-comparison gate would have to pin matplotlib into CI and would still
   be fragile. What is gated is the thing that actually rots: a figure drawn
   from evidence that has since changed, or from a script that has since
   changed.

## The second half of `--check`: provenance cross-checks

Hashes alone prove only that nothing moved. Each loader below additionally
re-derives, from the raw artifact, a number the *record* states in prose, and
raises `ProvenanceError` if the two disagree -- the coherent-sine FFT's
SNDR/ENOB/SFDR, the transfer bench's per-corner minimum adjacent-code gap,
the Monte Carlo max|INL| *and* max|DNL| mean/stdev/min/max. Those loaders are
stdlib-only, so `--check` runs them too. The effect is that a figure cannot
claim a record's authority unless this module can still reproduce that
record's own stated numbers from the committed artifacts.

A number a record states with a particular estimator is drawn with *that*
estimator (the Monte Carlo sigmas are the population values `run_mc.py`
prints into the record's own table, not the yield report's sample (n-1)
ones), and every sigma a figure prints names the estimator it is -- a plot
must not assert a number its own record does not, and two differently
estimated sigmas across the figure set must not look like one convention.

Each figure also prints its source **Record ID** and the record's own corner
set / statistical convention into the figure itself, so a plot cannot outlive
the PVT context it was measured in.

## What is NOT here, and why

* **No new evidence.** Nothing under `sim/<experiment>/` is written, and no
  verdict in `spec/` or `docs/characterization-report.md` moves. A figure
  showing a DRAFT row's measurement says DRAFT on its face.
* **No linearity derived from the 5-code transfer spot-check.** That bench
  measures 5 codes; its own record states that DR-003 defers the formal
  DNL/INL budget to the Monte Carlo campaign. The transfer figure therefore
  plots the measured levels and the monotonicity margin only -- INL/DNL comes
  from the Monte Carlo draws, in its own figure.
* **Rendering is not in CI.** matplotlib is pinned in
  `sim/report/plots-requirements.txt` and installed by whoever regenerates;
  CI only runs the stdlib `--check`.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PLOTS_DIR = REPO_ROOT / "docs" / "plots"
MANIFEST_PATH = PLOTS_DIR / "manifest.json"
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_REL = "sim/report/plots.py"
MANIFEST_REL = "docs/plots/manifest.json"
MANIFEST_SCHEMA_VERSION = 1

# `sim/full-conversion-transient/dynamic_enob.py` is the repository's own
# stdlib-only coherent-sampling FFT analyzer; the spectrum figure reuses it
# rather than carrying a second implementation of the same transform.
sys.path.insert(0, str(REPO_ROOT / "sim" / "full-conversion-transient"))


class ProvenanceError(RuntimeError):
    """A raw artifact no longer reproduces the number its record states."""


@dataclasses.dataclass(frozen=True)
class PlotSpec:
    """One figure: what it shows, which spec row it summarizes, and every
    committed file it is derived from (the source record first)."""

    key: str
    spec_row: str  # a `sim/report/manifest.py` row id
    title: str
    what: str  # one line, for `--list` and sim/README.md
    source_record: str  # repo-relative path to the evidence record
    extra_inputs: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        return f"{self.key}.svg"

    @property
    def rel_output(self) -> str:
        return f"docs/plots/{self.filename}"

    @property
    def inputs(self) -> tuple[str, ...]:
        return (self.source_record,) + self.extra_inputs


ENOB_SAMPLES = "sim/enob-estimate/yield-reports/20261008-233032-8bc3d1f.samples.json"
ENOB_YIELD = "sim/enob-estimate/yield-reports/20261008-233032-8bc3d1f.json"
CDAC_MC_YIELD = "sim/cdac-array-transfer/yield-reports/20261001-124049-5207381.json"

# The CDAC mismatch Monte Carlo campaign's own committed raw draw logs. Both
# per-draw statistics the INL/DNL figure plots are re-derived from these by
# the campaign's own parser, so the logs, that parser and the measure-parsing
# helper it calls are all hashed inputs of that figure.
CDAC_MC_RECORD_ID = "20261001-124049-5207381"
CDAC_MC_DRAW_DIR = f"sim/cdac-array-transfer/mc-draws/{CDAC_MC_RECORD_ID}"
CDAC_MC_N = 40  # the source record's own stated N; a missing log must fail the gate
# `run_mc.py` writes `draw_<index>_seed<seed>.log`, seeds running seed..seed+N-1
# from the record's stated seed=1 (`negctrl_*` logs are the mismatch-disabled
# control, not draws, and are deliberately not read here).
CDAC_MC_DRAW_LOGS = tuple(
    f"{CDAC_MC_DRAW_DIR}/draw_{index}_seed{index + 1}.log" for index in range(CDAC_MC_N)
)
CDAC_MC_PARSER = "sim/cdac-array-transfer/run_mc.py"
MEASURE_PARSER = "sim/harness/measure.py"
DYNAMIC_ENOB = "sim/full-conversion-transient/dynamic_enob.py"

TRANSFER_CORNER_DIR = "sim/cdac-array-transfer/corners/20261001-120402-d24f700"
TRANSFER_CORNERS = (
    "tt_27c_1.80v",
    "ss_27c_1.80v",
    "ff_27c_1.80v",
    "sf_27c_1.80v",
    "fs_27c_1.80v",
    "tt_-40c_1.80v",
    "tt_125c_1.80v",
    "tt_27c_1.62v",
    "tt_27c_1.98v",
)

PLOTS: tuple[PlotSpec, ...] = (
    PlotSpec(
        key="enob-distribution",
        spec_row="enob",
        title="ENOB — Monte Carlo distribution",
        what="per-draw achieved ENOB against the DRAFT lower limit",
        source_record="sim/enob-estimate/records/20261008-233032-8bc3d1f.md",
        extra_inputs=(ENOB_SAMPLES, ENOB_YIELD),
    ),
    PlotSpec(
        key="cdac-inl-distribution",
        spec_row="inl-dnl",
        title="CDAC max|INL| and max|DNL| — mismatch Monte Carlo distributions",
        what="per-draw worst-case |INL| and |DNL| against the DRAFT ±1 LSB target",
        source_record=f"sim/cdac-array-transfer/records/{CDAC_MC_RECORD_ID}.md",
        extra_inputs=(CDAC_MC_YIELD, CDAC_MC_PARSER, MEASURE_PARSER) + CDAC_MC_DRAW_LOGS,
    ),
    PlotSpec(
        key="cdac-transfer-spot-check",
        spec_row="sampling-cap",
        title="CDAC transfer — 5-code spot check across the ratified PVT grid",
        what="measured differential top-plate level per code, all 9 corners",
        source_record="sim/cdac-array-transfer/records/20261001-120402-d24f700.md",
        extra_inputs=tuple(
            f"{TRANSFER_CORNER_DIR}/{corner}.log" for corner in sorted(TRANSFER_CORNERS)
        ),
    ),
    PlotSpec(
        key="bit-trial-settling-corners",
        spec_row="sample-rate",
        title="CDAC bit-trial settling — corner spread vs the DR-006 phase budget",
        what="worst-case t_settle_99% per corner against the 83.333 ns budget",
        source_record="sim/cdac-bit-trial-settling/records/20261001-140017-7487784.md",
    ),
    PlotSpec(
        key="coherent-sine-spectrum",
        spec_row="enob",
        title="Coherent-sine output spectrum — measured vs ideal quantizer",
        what="single-sided spectrum of the captured 32-code record (N=32, bin 7)",
        source_record="sim/full-conversion-transient/records/20261106-193045-7bdf8c4.md",
        extra_inputs=(DYNAMIC_ENOB,),
    ),
)


# --------------------------------------------------------------------------
# Hashing and small record helpers (stdlib only -- the `--check` half)
# --------------------------------------------------------------------------


def sha256_bytes_file(path: Path) -> str:
    """Binary-safe SHA-256 of a file's raw bytes, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_field(path: Path, name: str) -> str | None:
    """A record's `- **<name>**: <value>` line, by `sim/README.md`'s "Base
    fields" convention.

    One widening over `sim/report/generate.py`'s `extract_field()`: a record
    may qualify a field name outside the bold span before the colon, as in
    `- **Measured value(s)** (`tt_27c_1.80v`): ...`. That qualifier is part of
    the *label*, not the value, so it is consumed here rather than left to
    make the field look absent.
    """
    pattern = (
        r"^-\s*\*\*" + re.escape(name) + r"\*\*\s*(?:\([^)\n]*\)\s*)?:\s*(.+)$"
    )
    match = re.search(pattern, path.read_text(), re.MULTILINE)
    return match.group(1).strip() if match else None


def record_context(rel_record: str) -> str:
    """The one-line PVT/statistical context a figure stamps on its own face.

    Tried in order: `Corner matrix run` (a PVT campaign), `Statistical
    convention` (a Monte Carlo record carries that instead -- `sim/README.md`
    "Monte Carlo records"), then `Estimate class` (a derived-estimate record
    states its population there). If none is present the figure says so
    plainly rather than printing an invented context.
    """
    path = REPO_ROOT / rel_record
    for field in ("Corner matrix run", "Statistical convention", "Estimate class"):
        value = _record_field(path, field)
        if value:
            return f"{field}: {_collapse(value, 170)}"
    return "corner/statistical context not stated as a base field in this record"


def record_id(rel_record: str) -> str:
    return _record_field(REPO_ROOT / rel_record, "Record ID") or Path(rel_record).stem


def _collapse(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _measures(log_text: str) -> dict[str, float]:
    """ngspice `.meas` results, as `{name: value}`.

    ngspice prints one `<name> = <value>` line per `.meas` statement in the
    batch log. Lines whose value is not a finite number (`failed`, and the
    informational `Reference value :` lines, which carry no name) are skipped
    rather than guessed at -- a caller that needs a missing name gets a
    KeyError, not a silent zero.
    """
    found: dict[str, float] = {}
    for match in re.finditer(
        r"^([a-z][a-z_0-9]*)\s*=\s*([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)\s*$",
        log_text,
        re.MULTILINE,
    ):
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if math.isfinite(value):
            found[match.group(1)] = value
    return found


def _markdown_table(text: str, header_contains: str) -> list[list[str]]:
    """The body rows of the first Markdown table whose header row contains
    `header_contains`, each row as a list of stripped cells.

    Records are hand-free generated documents with several tables; selecting
    by a distinctive header cell keeps a loader pinned to the table it means
    even if another table is appended above or below it later.
    """
    rows: list[list[str]] = []
    in_table = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        cells = _split_row(stripped)
        if not in_table:
            if header_contains in stripped:
                in_table = True
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _split_row(line: str) -> list[str]:
    """One Markdown table row's cells, honouring backslash-escaped pipes.

    `sim/` records legitimately contain `| max\\|INL\\| | 40 | ... |` -- a
    naive `split("|")` tears that first cell into three and silently shifts
    every column after it, so the escape is respected here and then undone in
    the cell text.
    """
    body = re.sub(r"^\|", "", line)
    body = re.sub(r"(?<!\\)\|$", "", body)
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", body)]


# --------------------------------------------------------------------------
# Loaders: committed artifact -> plottable data, with a provenance re-check
# --------------------------------------------------------------------------


def load_enob_distribution() -> dict:
    """Per-draw achieved ENOB and the DRAFT limit it is graded against.

    Source: the persisted `klt yield` samples document, which carries the 40
    per-draw `enob_bit` values, plus the yield report minted from it (for the
    distribution summary and the limits). Cross-check: the samples' own mean
    must reproduce the yield report's stated `distribution.mean`.

    The sigma drawn is the yield report's own `distribution.stddev`, which is
    the sample (n-1) estimator; the source record states no sigma of its own,
    so nothing is contradicted, but the figure labels which estimator it is
    (the INL/DNL figure labels the population one its record prints) rather
    than leaving two differently-estimated sigmas unmarked across the set.
    """
    samples_doc = json.loads((REPO_ROOT / ENOB_SAMPLES).read_text())
    report = json.loads((REPO_ROOT / ENOB_YIELD).read_text())
    measurement = _one_measurement(samples_doc, "enob_bit", ENOB_SAMPLES)
    reported = _one_measurement(report, "enob_bit", ENOB_YIELD)
    values = [float(v) for v in measurement["samples"]]
    _agree(
        "enob_bit mean",
        statistics.mean(values),
        float(reported["distribution"]["mean"]),
        tolerance=5e-7,
        where=f"{ENOB_SAMPLES} vs {ENOB_YIELD}",
    )
    limits = measurement.get("limits") or {}
    return {
        "values": values,
        "unit": measurement.get("unit", "bit"),
        "limit_min": limits.get("min"),
        "target_yield": limits.get("target_yield"),
        "mean": statistics.mean(values),
        "stdev": float(reported["distribution"]["stddev"]),
        "empirical_yield": reported["yield"]["empirical"]["estimate"],
        "yield_ci": reported["yield"]["empirical"]["confidence_interval"],
        "source_record_stamp": measurement.get("source_record"),
    }


def _load_cdac_run_mc():
    """Import `sim/cdac-array-transfer/run_mc.py` by path for its pure raw-log
    parser `_parse_draw()` -- the campaign's own DNL/INL computation, the one
    that minted the record's table. Its directory name has a hyphen, so it is
    not importable as a package; `sim/enob-estimate/run_enob.py` loads it the
    same way for the same reason. No ngspice is invoked, nothing is written.
    """
    import importlib.util  # noqa: PLC0415  (kept local: stdlib `--check` path)

    cdac_dir = REPO_ROOT / "sim" / "cdac-array-transfer"
    module_spec = importlib.util.spec_from_file_location("cdac_run_mc", cdac_dir / "run_mc.py")
    module = importlib.util.module_from_spec(module_spec)
    # run_mc.py imports its sibling gen_fragment.py and sim/harness/ by bare name.
    sys.modules["cdac_run_mc"] = module
    sys.path.insert(0, str(cdac_dir))
    try:
        module_spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(cdac_dir))
    return module


def _cdac_mc_stated_rows(record_path: Path) -> dict[str, list[str]]:
    """The source record's own "DNL/INL distributions" table, by statistic."""
    stated = {}
    for cells in _markdown_table(record_path.read_text(), "statistic"):
        if len(cells) >= 6:
            stated[cells[0]] = cells[1:]
    for name in ("max|DNL|", "max|INL|"):
        if name not in stated:
            raise ProvenanceError(
                f"{record_path.relative_to(REPO_ROOT)}: no {name!r} row in the "
                "DNL/INL distributions table -- the record's table shape changed, so "
                "this figure's provenance cross-check can no longer be made"
            )
    return stated


def load_cdac_inl_distribution() -> dict:
    """Per-draw worst-case |INL| AND |DNL| from the CDAC mismatch Monte Carlo
    campaign's own committed raw draw logs.

    Both series are re-derived here from
    `sim/cdac-array-transfer/mc-draws/<record-id>/draw_*.log` -- the campaign's
    40 committed per-draw ngspice logs -- by that experiment's own
    `run_mc._parse_draw()`, the same pure parser `run_mc.reanalyze_from_logs()`
    and `sim/enob-estimate/run_enob.py` use, and the same computation that
    minted the record's table. The campaign's yield report supplies only the
    DRAFT limit, the empirical yields and their Clopper-Pearson intervals; its
    persisted `samples` path is a scratch file, but that costs this figure
    nothing, because the per-draw values do not come from it.

    Cross-check: for BOTH statistics, the mean / stdev / min / max this module
    derives from the raw logs must reproduce the four the record's own
    "DNL/INL distributions" table states, at the record's printed precision.
    `stdev` is the POPULATION standard deviation, which is the estimator
    `run_mc.py` prints into that table (`statistics.pstdev`); the figure draws
    the record's value, not a different estimator's.
    """
    mc = _load_cdac_run_mc()
    inl_values: list[float] = []
    dnl_values: list[float] = []
    for rel in CDAC_MC_DRAW_LOGS:
        path = REPO_ROOT / rel
        name_match = mc._LOG_NAME_RE.match(path.name)
        if name_match is None or name_match.group("kind") != "draw":
            raise ProvenanceError(f"{rel}: not a `run_mc.py` mismatch draw log")
        draw = mc._parse_draw(int(name_match.group("seed")), path.read_text())
        if not (math.isfinite(draw.inl_max_lsb) and math.isfinite(draw.dnl_max_lsb)):
            raise ProvenanceError(
                f"{rel}: a code measurement is missing from the log, so this draw's "
                f"max|INL| ({draw.inl_max_lsb}) / max|DNL| ({draw.dnl_max_lsb}) is not finite"
            )
        inl_values.append(draw.inl_max_lsb)
        dnl_values.append(draw.dnl_max_lsb)

    report = json.loads((REPO_ROOT / CDAC_MC_YIELD).read_text())
    by_name = {m["name"]: m for m in report["measurements"]}
    record_path = REPO_ROOT / f"sim/cdac-array-transfer/records/{CDAC_MC_RECORD_ID}.md"
    stated = _cdac_mc_stated_rows(record_path)

    series = {}
    for key, row_name, measurement_name, values in (
        ("inl", "max|INL|", "inl_max_lsb", inl_values),
        ("dnl", "max|DNL|", "dnl_max_lsb", dnl_values),
    ):
        row = stated[row_name]
        if int(row[0]) != len(values):
            raise ProvenanceError(
                f"{row_name}: this module read {len(values)} committed draw logs from "
                f"{CDAC_MC_DRAW_DIR} but {record_path.relative_to(REPO_ROOT)} states "
                f"N = {row[0]}"
            )
        derived = {
            "mean": statistics.fmean(values),
            "stdev": statistics.pstdev(values),
            "min": min(values),
            "max": max(values),
        }
        # The record prints 4 decimals; compare at that precision only.
        for label, column in (("mean", 1), ("stdev", 2), ("min", 3), ("max", 4)):
            _agree(
                f"{row_name} {label}",
                round(derived[label], 4),
                float(row[column]),
                tolerance=1e-9,
                where=(
                    f"{CDAC_MC_DRAW_DIR}/draw_*.log via run_mc._parse_draw() vs "
                    f"{record_path.relative_to(REPO_ROOT)}"
                ),
            )
        measurement = by_name[measurement_name]
        empirical = measurement["yield"]["empirical"]
        series[key] = {
            **derived,
            "values": values,
            "label": row_name,
            "unit": measurement.get("unit", "LSB"),
            "limit_max": (measurement.get("limits") or {}).get("max"),
            "yield": empirical["estimate"],
            "yield_ci": empirical["confidence_interval"],
            "yield_confidence": empirical["confidence"],
        }
    return {
        "n": len(inl_values),
        "series": series,
        "draw_dir": CDAC_MC_DRAW_DIR,
        "sample_size_verdicts": sorted(
            {
                str((by_name[name].get("sample_size") or {}).get("verdict"))
                for name in ("inl_max_lsb", "dnl_max_lsb")
            }
        ),
    }


def load_cdac_transfer() -> dict:
    """Measured differential top-plate level per code, per corner.

    Source: the nine committed ngspice batch logs of the ratified-grid
    transfer run. Each log carries `vtop_p_<code>` / `vtop_n_<code>` `.meas`
    results for the bench's 5 spot-check codes; the differential level is
    their difference.

    Cross-check: the smallest adjacent-code gap this module computes per
    corner must reproduce the gap the record's own per-corner table states
    (5 decimals) -- the number that record's monotonicity verdict rests on.
    """
    record_path = REPO_ROOT / "sim/cdac-array-transfer/records/20261001-120402-d24f700.md"
    stated = {}
    for cells in _markdown_table(record_path.read_text(), "min adjacent-code gap"):
        if len(cells) >= 4:
            stated[cells[0].strip("`")] = cells[3]

    corners: dict[str, dict] = {}
    for corner in TRANSFER_CORNERS:
        log = REPO_ROOT / TRANSFER_CORNER_DIR / f"{corner}.log"
        measures = _measures(log.read_text())
        codes = sorted(
            int(name.rsplit("_", 1)[1]) for name in measures if name.startswith("vtop_p_")
        )
        if not codes:
            raise ProvenanceError(
                f"{log.relative_to(REPO_ROOT)}: no `vtop_p_<code>` .meas result -- "
                "the transfer bench's measurement names changed"
            )
        vdiff = [measures[f"vtop_p_{code}"] - measures[f"vtop_n_{code}"] for code in codes]
        gaps = [later - earlier for earlier, later in zip(vdiff, vdiff[1:])]
        if corner in stated:
            _agree(
                f"{corner} min adjacent-code gap",
                round(min(gaps), 5),
                float(stated[corner]),
                tolerance=1e-9,
                where=f"{log.relative_to(REPO_ROOT)} vs {record_path.relative_to(REPO_ROOT)}",
            )
        corners[corner] = {"codes": codes, "vdiff": vdiff, "min_gap": min(gaps)}

    missing = sorted(set(stated) - set(corners))
    if missing:
        raise ProvenanceError(
            f"{record_path.relative_to(REPO_ROOT)} states corner(s) {missing} that this "
            "figure does not read -- add their logs to the figure's inputs or the plot "
            "would show fewer corners than the record grades"
        )
    return {"corners": corners, "n_codes": len(next(iter(corners.values()))["codes"])}


def load_bit_trial_settling() -> dict:
    """Worst-case 99% settling time per corner, and the budget it is read
    against.

    Source: the campaign record's own per-corner worst-case table (the raw
    artifacts committed for this campaign are the frozen decks, not logs, so
    the record's generated table is the committed structured form of this
    measurement). The DR-006-derived worst-case phase budget is read out of
    the record's prose rather than hard-coded here.

    Cross-check: budget / t_settle must reproduce the margin the same table
    states, to that column's own 1-decimal precision.
    """
    record_path = REPO_ROOT / "sim/cdac-bit-trial-settling/records/20261001-140017-7487784.md"
    text = record_path.read_text()
    budget_match = re.search(
        r"\*\*DR-006 phase-period reference points\*\*:\s*([\d.]+)\s*ns", text
    )
    if budget_match is None:
        raise ProvenanceError(
            f"{record_path.relative_to(REPO_ROOT)}: the DR-006 phase-period reference "
            "point is no longer stated in the shape this figure reads it from"
        )
    budget_ns = float(budget_match.group(1))

    points = []
    for cells in _markdown_table(text, "t_settle_99%"):
        if len(cells) < 5:
            continue
        corner = cells[0].strip("`")
        t_settle = float(cells[3])
        stated_margin = float(cells[4].rstrip("x"))
        _agree(
            f"{corner} margin vs the DR-006 budget",
            round(budget_ns / t_settle, 1),
            stated_margin,
            tolerance=1e-9,
            where=f"{record_path.relative_to(REPO_ROOT)} (recomputed from its own columns)",
        )
        points.append(
            {
                "corner": corner,
                "bit": cells[1],
                "direction": cells[2],
                "t_settle_ns": t_settle,
                "margin": stated_margin,
                "rows_measured": cells[5] if len(cells) > 5 else "",
            }
        )
    if not points:
        raise ProvenanceError(
            f"{record_path.relative_to(REPO_ROOT)}: no per-corner worst-case settling rows "
            "parsed -- the record's table shape changed"
        )
    return {"points": points, "budget_ns": budget_ns}


def load_coherent_sine_spectrum() -> dict:
    """The captured code stream's single-sided spectrum, measured and ideal.

    Source: the dynamic-test record's own "Captured code stream" table (one
    ideal and one captured code per conversion). The transform is this
    repository's committed stdlib analyzer,
    `sim/full-conversion-transient/dynamic_enob.py`, so the figure and the
    record's headline figures come out of one implementation.

    Cross-check: the SNDR, ENOB, SFDR, spur bin and full-scale-normalised
    ENOB this module recomputes must reproduce the values the record states,
    to the record's own printed precision.
    """
    import dynamic_enob  # stdlib-only; path set at module import

    record_path = REPO_ROOT / "sim/full-conversion-transient/records/20261106-193045-7bdf8c4.md"
    text = record_path.read_text()
    captured: list[int] = []
    ideal: list[int] = []
    for cells in _markdown_table(text, "captured code"):
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        ideal.append(int(cells[3]))
        captured.append(int(cells[4]))

    meta = _record_field(record_path, "Dynamic-test (FFT) metadata") or ""
    bin_match = re.search(r"coherent bin\s*=\s*(\d+)", meta)
    n_match = re.search(r"N\s*=\s*(\d+)\s*samples", meta)
    fs_match = re.search(r"f_s\s*=\s*([\d.]+)\s*MS/s", meta)
    if not (bin_match and n_match):
        raise ProvenanceError(
            f"{record_path.relative_to(REPO_ROOT)}: the FFT metadata field no longer "
            "states N and the coherent bin in the shape this figure reads"
        )
    tone_bin, n_stated = int(bin_match.group(1)), int(n_match.group(1))
    if len(captured) != n_stated:
        raise ProvenanceError(
            f"{record_path.relative_to(REPO_ROOT)}: the captured code-stream table has "
            f"{len(captured)} row(s) but the record states N = {n_stated}"
        )

    n_bits = 10
    measured = dynamic_enob.analyze(captured, tone_bin, n_bits)
    reference = dynamic_enob.analyze(ideal, tone_bin, n_bits)

    values = _record_field(record_path, "Measured value(s)") or ""
    for label, derived, pattern, places in (
        ("SNDR", measured["sndr_db"], r"SNDR = \*\*([\d.]+) dB\*\*", 2),
        ("ENOB", measured["enob_bit"], r"ENOB = \*\*([\d.]+) bit\*\*", 3),
        ("SFDR", measured["sfdr_db"], r"SFDR = ([\d.]+) dB", 2),
        (
            "full-scale-normalised ENOB",
            measured["enob_fs_bit"],
            r"full-scale-normalised ENOB = \*\*([\d.]+) bit\*\*",
            3,
        ),
        ("spur bin", float(measured["spur_bin"]), r"largest spur bin (\d+)", 0),
    ):
        match = re.search(pattern, values)
        if match is None:
            raise ProvenanceError(
                f"{record_path.relative_to(REPO_ROOT)}: the record's Measured value(s) "
                f"field no longer states {label} in the shape this figure reads"
            )
        _agree(
            f"coherent-sine {label}",
            round(derived, places),
            float(match.group(1)),
            tolerance=1e-9,
            where=f"recomputed from the record's own code-stream table via {SCRIPT_REL}",
        )

    full_scale_ms = measured["full_scale_amplitude_codes"] ** 2 / 2.0
    return {
        "measured": measured,
        "ideal": reference,
        "measured_dbfs": _to_dbfs(measured["spectrum"], full_scale_ms),
        "ideal_dbfs": _to_dbfs(reference["spectrum"], full_scale_ms),
        "tone_bin": tone_bin,
        "n": n_stated,
        "n_bits": n_bits,
        "fs_msps": float(fs_match.group(1)) if fs_match else None,
    }


def _to_dbfs(spectrum: list[float], full_scale_mean_square: float) -> list[float]:
    """Power bins in dB relative to a full-scale sine's mean-square value.

    An exactly-zero bin has no finite dB value; it is floored 10 dB below the
    smallest non-zero bin in the same record so it draws at the bottom of the
    axis instead of at minus infinity.
    """
    non_zero = [p for p in spectrum if p > 0.0]
    floor_db = (
        10.0 * math.log10(min(non_zero) / full_scale_mean_square) - 10.0 if non_zero else -200.0
    )
    return [
        10.0 * math.log10(p / full_scale_mean_square) if p > 0.0 else floor_db for p in spectrum
    ]


def _one_measurement(document: dict, name: str, where: str) -> dict:
    for measurement in document.get("measurements", []):
        if measurement.get("name") == name:
            return measurement
    raise ProvenanceError(f"{where}: no measurement named {name!r}")


def _agree(label: str, derived: float, stated: float, tolerance: float, where: str) -> None:
    if abs(derived - stated) > tolerance:
        raise ProvenanceError(
            f"{label}: this module derives {derived!r} from the committed artifact but the "
            f"record states {stated!r} ({where}). The figure is not drawn: either the "
            "artifact or the parse changed, and a plot must not assert a number its own "
            "record does not."
        )


LOADERS = {
    "enob-distribution": load_enob_distribution,
    "cdac-inl-distribution": load_cdac_inl_distribution,
    "cdac-transfer-spot-check": load_cdac_transfer,
    "bit-trial-settling-corners": load_bit_trial_settling,
    "coherent-sine-spectrum": load_coherent_sine_spectrum,
}


# --------------------------------------------------------------------------
# Spec-row labelling (shared by `--render` and `--check`)
# --------------------------------------------------------------------------


def spec_row_label(row_id: str) -> str:
    """`<Spec row name> — <status>`, read out of `sim/report/manifest.py`.

    Read rather than transcribed for the same reason the characterization
    report re-extracts its citations: a figure must not keep asserting DRAFT
    (or RATIFIED) after the manifest row it summarizes has moved. Raises
    KeyError for a row id the manifest does not define, so a typo in a
    `PlotSpec` fails the gate instead of printing a blank caption.
    """
    sys.path.insert(0, str(REPO_ROOT / "sim"))
    from report import manifest  # noqa: PLC0415  (kept local: see module docstring)

    for row in manifest.ROWS:
        if row.id == row_id:
            return f"{row.spec_row} — {row.status}"
    raise KeyError(
        f"spec row id {row_id!r} is not in sim/report/manifest.ROWS "
        f"(known: {sorted(r.id for r in manifest.ROWS)})"
    )


def caption(spec: PlotSpec) -> str:
    """The provenance footer stamped onto every figure."""
    return (
        f"spec/target-spec.md row: {spec_row_label(spec.spec_row)}    |    "
        f"source record {record_id(spec.source_record)}  ({spec.source_record})\n"
        f"{record_context(spec.source_record)}\n"
        f"Derived view of committed evidence — rendered by {SCRIPT_REL}; "
        f"regenerable, not itself evidence. No simulation was run to draw it."
    )


# --------------------------------------------------------------------------
# Renderers (matplotlib; reached only from `--render`)
# --------------------------------------------------------------------------

FIGSIZE = (9.0, 5.6)
NOMINAL_CORNER = "tt_27c_1.80v"


def _new_figure(plt):
    fig = plt.figure(figsize=FIGSIZE)
    return fig


def _finish(fig, spec: PlotSpec) -> None:
    fig.text(
        0.012,
        0.012,
        caption(spec),
        fontsize=6.0,
        color="#333333",
        va="bottom",
        ha="left",
        linespacing=1.5,
    )
    fig.subplots_adjust(bottom=0.26, top=0.88)


def draw_enob_distribution(plt, spec: PlotSpec, data: dict):
    fig = _new_figure(plt)
    axis = fig.add_subplot(111)
    values, unit = data["values"], data["unit"]
    axis.hist(
        values,
        bins=12,
        color="#4c72b0",
        edgecolor="white",
        linewidth=0.7,
        label=f"{len(values)} Monte Carlo draws",
    )
    axis.axvline(
        data["mean"],
        color="#1a1a1a",
        linestyle="-",
        linewidth=1.4,
        label=(
            f"mean = {data['mean']:.3f} {unit} "
            f"(σ = {data['stdev']:.3f}, sample n−1 — the yield report's estimator)"
        ),
    )
    if data["limit_min"] is not None:
        axis.axvline(
            data["limit_min"],
            color="#c44e52",
            linestyle="--",
            linewidth=1.6,
            label=(
                f"DRAFT lower limit = {data['limit_min']:g} {unit} "
                f"(target yield {data['target_yield']:.0%})"
            ),
        )
    low, high = data["yield_ci"]["low"], data["yield_ci"]["high"]
    axis.set_title(
        f"{spec.title}\nempirical yield above the limit "
        f"{data['empirical_yield']:.0%} (95% CI {low:.0%}–{high:.0%}, N = {len(values)})",
        fontsize=11,
    )
    axis.set_xlabel(f"achieved ENOB ({unit})")
    axis.set_ylabel("draws per bin (count)")
    axis.set_ylim(top=axis.get_ylim()[1] * 1.3)  # headroom: legend over bars
    axis.legend(fontsize=7.5, loc="upper left", framealpha=0.9)
    axis.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.6)
    _finish(fig, spec)
    return fig


def draw_cdac_inl_distribution(plt, spec: PlotSpec, data: dict):
    """Both per-draw distributions, one panel each, on a shared axis.

    Every number drawn here is the source record's own: the mean / sigma /
    min / max are re-derived from the campaign's committed draw logs and
    cross-checked against the record's table before the figure is drawn
    (`load_cdac_inl_distribution`), and sigma is the population estimator the
    record itself prints -- labelled as such, so the figure cannot be read as
    asserting the sample (n-1) value.
    """
    fig = _new_figure(plt)
    top = fig.add_subplot(211)
    bottom = fig.add_subplot(212, sharex=top)
    series = data["series"]
    n = data["n"]

    for axis, key, color in ((top, "inl", "#55a868"), (bottom, "dnl", "#4c72b0")):
        entry = series[key]
        unit = entry["unit"]
        axis.hist(
            entry["values"],
            bins=12,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            label=f"{n} mismatch draws",
        )
        axis.axvline(
            entry["mean"],
            color="#1a1a1a",
            linewidth=1.4,
            label=(
                f"mean = {entry['mean']:.4f} {unit} "
                f"(σ = {entry['stdev']:.4f}, population — the record's estimator)"
            ),
        )
        if entry["limit_max"] is not None:
            axis.axvline(
                entry["limit_max"],
                color="#c44e52",
                linestyle="--",
                linewidth=1.6,
                label=f"DRAFT target = ±{entry['limit_max']:g} {unit} (not ratified)",
            )
        low, high = entry["yield_ci"]["low"], entry["yield_ci"]["high"]
        axis.set_title(
            f"{entry['label']} — within the DRAFT target in {entry['yield']:.1%} of draws "
            f"({entry['yield_confidence']:.0%} CI {low:.1%}–{high:.1%})",
            fontsize=9,
        )
        axis.set_ylabel("draws per bin", fontsize=9)
        axis.set_ylim(top=axis.get_ylim()[1] * 1.45)  # headroom: legend over bars
        axis.legend(fontsize=6.6, loc="upper right", framealpha=0.9)
        axis.grid(axis="y", linestyle=":", linewidth=0.6, alpha=0.6)
        axis.tick_params(labelsize=8)

    bottom.set_xlabel(
        f"worst-case deviation across the sampled code set ({series['inl']['unit']})", fontsize=9
    )
    fig.suptitle(spec.title, fontsize=11, y=0.965)
    fig.subplots_adjust(hspace=0.42)
    verdicts = "/".join(data["sample_size_verdicts"])
    fig.text(
        0.012,
        0.095,
        f"Both distributions are re-derived from this campaign's own {n} committed raw draw "
        f"logs ({data['draw_dir']}/draw_*.log),\n"
        "parsed by its own run_mc._parse_draw() — the computation that minted the record's "
        "table, which each number above is checked against\n"
        f"before the figure is drawn. The record grades both sample sizes \"{verdicts}\" for a "
        f"±1 percentage-point yield estimate at "
        f"{series['inl']['yield_confidence']:.0%} confidence: read the yields as indicative.",
        fontsize=6.2,
        color="#333333",
        va="bottom",
        ha="left",
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#f4f4f4", edgecolor="#cccccc"),
    )
    _finish(fig, spec)
    return fig


def draw_cdac_transfer(plt, spec: PlotSpec, data: dict):
    fig = _new_figure(plt)
    left = fig.add_subplot(121)
    right = fig.add_subplot(122)
    colormap = plt.get_cmap("tab10")
    corners = list(data["corners"])
    for index, corner in enumerate(corners):
        point = data["corners"][corner]
        nominal = corner == NOMINAL_CORNER
        left.plot(
            point["codes"],
            point["vdiff"],
            marker="o",
            markersize=3.5,
            linewidth=2.2 if nominal else 1.0,
            color=colormap(index % 10),
            alpha=1.0 if nominal else 0.85,
            label=f"{corner}{' (nominal)' if nominal else ''}",
        )
    left.axhline(0.0, color="#999999", linewidth=0.8, linestyle=":")
    left.set_title(
        f"measured level at each of {data['n_codes']} codes, {len(corners)} corners",
        fontsize=9.5,
    )
    left.set_xlabel("CDAC input code (of the 9-bit sub-array)")
    left.set_ylabel("differential top-plate level\nV(top_p) − V(top_n)   (V)")
    left.legend(fontsize=6.0, loc="upper left", framealpha=0.9)
    left.grid(linestyle=":", linewidth=0.6, alpha=0.6)

    order = sorted(corners, key=lambda c: data["corners"][c]["min_gap"])
    gaps = [data["corners"][c]["min_gap"] for c in order]
    bars = right.barh(range(len(order)), gaps, color="#8172b2", height=0.62)
    right.set_yticks(range(len(order)))
    right.set_yticklabels(order, fontsize=7)
    right.invert_yaxis()
    right.set_xlabel("smallest adjacent-code gap at that corner  (V)")
    right.set_title(
        "monotonicity margin — every gap > 0 is monotonic",
        fontsize=9.5,
    )
    right.set_xlim(0.0, max(gaps) * 1.22)
    for bar, gap in zip(bars, gaps):
        right.text(
            gap * 1.02,
            bar.get_y() + bar.get_height() / 2,
            f"{gap:.5f} V",
            va="center",
            fontsize=6.5,
        )
    right.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.6)

    fig.suptitle(spec.title, fontsize=11, y=0.965)
    fig.text(
        0.5,
        0.895,
        f"Linearity is NOT derived here: this bench measures {data['n_codes']} codes, and "
        "DR-003 defers the\nDNL/INL budget to the Monte Carlo campaign — see "
        "cdac-inl-distribution.svg",
        fontsize=8.0,
        color="#444444",
        ha="center",
        va="top",
        linespacing=1.4,
    )
    _finish(fig, spec)
    fig.subplots_adjust(left=0.105, right=0.975, wspace=0.34, top=0.80)
    return fig


def draw_bit_trial_settling(plt, spec: PlotSpec, data: dict):
    fig = _new_figure(plt)
    axis = fig.add_subplot(111)
    points = sorted(data["points"], key=lambda p: -p["t_settle_ns"])
    labels = [p["corner"] for p in points]
    times = [p["t_settle_ns"] for p in points]
    budget = data["budget_ns"]
    colors = ["#c44e52" if label == labels[0] else "#4c72b0" for label in labels]
    bars = axis.barh(range(len(points)), times, color=colors, height=0.62)
    axis.axvline(
        budget,
        color="#1a1a1a",
        linestyle="--",
        linewidth=1.8,
        label=f"DR-006-derived worst-case phase budget = {budget:g} ns (12 MHz)",
    )
    for bar, point in zip(bars, points):
        axis.text(
            point["t_settle_ns"] + budget * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{point['t_settle_ns']:.3f} ns  ({point['margin']:.1f}× margin, "
            f"bit {point['bit']}/{point['direction']})",
            va="center",
            fontsize=6.8,
        )
    axis.set_yticks(range(len(points)))
    axis.set_yticklabels(labels, fontsize=7.5)
    axis.invert_yaxis()
    axis.set_xlim(0.0, budget * 1.08)
    axis.set_xlabel("worst-case 99% settling time of the shared top-plate node  (ns)")
    axis.set_ylabel("PVT corner point (one-at-a-time grid)")
    axis.set_title(
        f"{spec.title}\nbinding corner {labels[0]} at {times[0]:.3f} ns — "
        f"{min(p['margin'] for p in points):.1f}× inside the budget; "
        f"worst-to-best spread {max(times) / min(times):.2f}×",
        fontsize=11,
    )
    axis.legend(fontsize=7.5, loc="lower right", framealpha=0.9)
    axis.grid(axis="x", linestyle=":", linewidth=0.6, alpha=0.6)
    _finish(fig, spec)
    return fig


def draw_coherent_sine_spectrum(plt, spec: PlotSpec, data: dict):
    fig = _new_figure(plt)
    axis = fig.add_subplot(111)
    measured, ideal = data["measured"], data["ideal"]
    bins = list(range(len(data["measured_dbfs"])))
    axis.plot(
        bins,
        data["ideal_dbfs"],
        drawstyle="steps-mid",
        color="#999999",
        linewidth=1.0,
        linestyle="--",
        label=(
            f"ideal {data['n_bits']}-bit quantizer, identical plan: "
            f"SNDR {ideal['sndr_db']:.2f} dB, ENOB {ideal['enob_bit']:.3f} bit"
        ),
    )
    axis.plot(
        bins,
        data["measured_dbfs"],
        drawstyle="steps-mid",
        color="#4c72b0",
        linewidth=1.6,
        label=(
            f"captured stream: SNDR {measured['sndr_db']:.2f} dB, "
            f"ENOB {measured['enob_bit']:.3f} bit, SFDR {measured['sfdr_db']:.2f} dB"
        ),
    )
    axis.plot(
        [data["tone_bin"]],
        [data["measured_dbfs"][data["tone_bin"]]],
        marker="v",
        color="#55a868",
        markersize=8,
        linestyle="none",
        label=f"input tone, bin {data['tone_bin']} ({measured['amplitude_dbfs']:.2f} dBFS)",
    )
    axis.plot(
        [measured["spur_bin"]],
        [data["measured_dbfs"][measured["spur_bin"]]],
        marker="v",
        color="#c44e52",
        markersize=8,
        linestyle="none",
        label=f"largest spur, bin {measured['spur_bin']}",
    )
    fs_text = f", f_s = {data['fs_msps']:g} MS/s" if data["fs_msps"] else ""
    axis.set_title(
        f"{spec.title}\n"
        f"N = {data['n']} coherently-sampled codes, no window{fs_text}\n"
        "single-corner pilot — INFORMATIONAL CROSS-CHECK, grades no spec row",
        fontsize=10,
    )
    axis.set_xlabel(
        f"FFT bin  (bin k = k · f_s / {data['n']}; bin 0 is DC and is excluded "
        "from both signal and noise)"
    )
    axis.set_ylabel("bin power relative to a full-scale sine  (dBFS)")
    axis.set_xlim(-0.5, len(bins) - 0.5)
    axis.set_xticks(bins)
    axis.legend(fontsize=7.0, loc="center left", framealpha=0.95)
    axis.grid(linestyle=":", linewidth=0.6, alpha=0.6)
    _finish(fig, spec)
    return fig


RENDERERS = {
    "enob-distribution": draw_enob_distribution,
    "cdac-inl-distribution": draw_cdac_inl_distribution,
    "cdac-transfer-spot-check": draw_cdac_transfer,
    "bit-trial-settling-corners": draw_bit_trial_settling,
    "coherent-sine-spectrum": draw_coherent_sine_spectrum,
}


# --------------------------------------------------------------------------
# Render + manifest
# --------------------------------------------------------------------------

MANIFEST_NOTE = (
    "Staleness manifest for the summary plots (issue #835). Written by "
    "`python3 sim/report/plots.py --render` and checked by `--check`, which "
    "`python3 sim/report/generate.py --check` (npm run check:report, part of "
    "npm run check:ci) calls. The SVGs beside this file are a regenerable "
    "DERIVED VIEW of committed evidence, never evidence themselves: nothing "
    "here is cited by signoff/block-manifest.json, and docs/plots/ is outside "
    "every path sim/check_append_only.py and signoff/check_evidence_hashes.py "
    "protect. Hashes are SHA-256 over raw bytes. The check does not re-render "
    "and compare bytes -- SVG output is not expected to be stable across "
    "matplotlib and font versions -- so rendering needs no CI dependency; see "
    "sim/report/plots-requirements.txt and sim/README.md 'Summary plots'."
)


def render_all(output_dir: Path = PLOTS_DIR) -> dict:
    """Render every plot into `output_dir` and return the manifest written.

    Imports matplotlib lazily: the `--check` half of this module must keep
    working on a checkout that has no rendering dependency installed.
    """
    try:
        import matplotlib
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "rendering needs matplotlib, which is deliberately NOT a CI "
            "dependency of this repository. Install the pin into a venv:\n"
            "    python3 -m venv .venv-plots\n"
            "    .venv-plots/bin/pip install -r sim/report/plots-requirements.txt\n"
            "    .venv-plots/bin/python sim/report/plots.py --render\n"
            f"(underlying import error: {exc})"
        ) from exc

    matplotlib.use("svg")  # head-less: no display, no interactive backend
    # Deterministic output for a fixed matplotlib version: a fixed salt pins
    # the generated element ids, `Date: None` drops the creation timestamp,
    # and `fonttype="none"` keeps labels as text (greppable, and independent
    # of which fonts the rendering host has).
    matplotlib.rcParams["svg.hashsalt"] = "sky130-sar-adc/docs/plots"
    matplotlib.rcParams["svg.fonttype"] = "none"
    matplotlib.rcParams["figure.dpi"] = 110
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    entries: dict[str, dict] = {}
    for spec in PLOTS:
        data = LOADERS[spec.key]()
        figure = RENDERERS[spec.key](plt, spec, data)
        target = output_dir / spec.filename
        figure.savefig(target, format="svg", metadata={"Date": None})
        plt.close(figure)
        entries[spec.key] = {
            "file": spec.rel_output,
            "title": spec.title,
            "what": spec.what,
            "spec_row": spec.spec_row,
            "spec_row_label": spec_row_label(spec.spec_row),
            "source_record": spec.source_record,
            "source_record_id": record_id(spec.source_record),
            "output_sha256": sha256_bytes_file(target),
            "inputs": {rel: sha256_bytes_file(REPO_ROOT / rel) for rel in spec.inputs},
        }

    manifest_document = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "note": MANIFEST_NOTE,
        "generator": SCRIPT_REL,
        "generator_sha256": sha256_bytes_file(SCRIPT_PATH),
        "plots": entries,
    }
    (output_dir / MANIFEST_PATH.name).write_text(
        json.dumps(manifest_document, indent=2, sort_keys=False) + "\n"
    )
    return manifest_document


# --------------------------------------------------------------------------
# The gate (`--check`): stdlib only, no matplotlib, no re-render
# --------------------------------------------------------------------------


def check(
    specs: tuple[PlotSpec, ...] = PLOTS,
    repo_root: Path = REPO_ROOT,
    plots_dir: Path = PLOTS_DIR,
    script_path: Path = SCRIPT_PATH,
) -> list[str]:
    """Every staleness problem, hash and provenance (empty == fresh).

    `hash_problems()` below is the half a unit test can drive against a
    synthetic fixture; `provenance_problems()` necessarily reads this
    repository's own records. `--check` runs both.
    """
    problems = hash_problems(specs, repo_root, plots_dir, script_path)
    if repo_root == REPO_ROOT:
        problems.extend(provenance_problems(specs))
    return problems


def hash_problems(
    specs: tuple[PlotSpec, ...],
    repo_root: Path,
    plots_dir: Path,
    script_path: Path,
) -> list[str]:
    """Hash-staleness problems only -- no record parsing, no matplotlib.

    Fails on each of the five ways a committed figure can stop matching what
    it was rendered from:

    1. the renderer changed (`generator_sha256`);
    2. a committed evidence input changed, vanished, or was added/dropped
       from a plot's input set;
    3. a committed SVG changed or vanished;
    4. a `docs/plots/*.svg` exists that no manifest entry claims;
    5. the manifest's plot set is not the renderer's plot set.

    Every parameter is injected so a unit test can point the whole gate at a
    temporary directory (see `sim/tests/test_report_plots.py`).
    """
    manifest_path = plots_dir / MANIFEST_PATH.name
    problems: list[str] = []
    if not manifest_path.is_file():
        return [
            f"{_rel(manifest_path, repo_root)} does not exist -- run "
            f"`python3 {SCRIPT_REL} --render` (see sim/README.md 'Summary plots')."
        ]
    try:
        document = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{_rel(manifest_path, repo_root)} is not valid JSON: {exc}"]

    version = document.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        problems.append(
            f"{_rel(manifest_path, repo_root)}: schema_version is {version!r}, expected "
            f"{MANIFEST_SCHEMA_VERSION!r} -- regenerate it."
        )
    recorded_script = document.get("generator_sha256")
    actual_script = sha256_bytes_file(script_path)
    if recorded_script != actual_script:
        problems.append(
            f"{SCRIPT_REL} has changed since the plots were rendered "
            f"(manifest records {_short(recorded_script)}, file is {_short(actual_script)}) "
            f"-- re-render so the committed figures are what this script now draws."
        )

    entries = document.get("plots")
    if not isinstance(entries, dict):
        return problems + [f"{_rel(manifest_path, repo_root)}: no `plots` object."]

    expected = {spec.key: spec for spec in specs}
    for key in sorted(set(expected) - set(entries)):
        problems.append(
            f"plot {key!r} is defined in {SCRIPT_REL} but absent from "
            f"{_rel(manifest_path, repo_root)} -- re-render."
        )
    for key in sorted(set(entries) - set(expected)):
        problems.append(
            f"{_rel(manifest_path, repo_root)} has an entry for {key!r}, which {SCRIPT_REL} "
            "no longer defines -- re-render (which drops it) and delete the orphaned SVG."
        )

    for key in sorted(set(expected) & set(entries)):
        problems.extend(
            _check_entry(expected[key], entries[key], manifest_path, repo_root)
        )

    claimed = {entry.get("file") for entry in entries.values() if isinstance(entry, dict)}
    for svg in sorted(plots_dir.glob("*.svg")):
        if _rel(svg, repo_root) not in claimed:
            problems.append(
                f"{_rel(svg, repo_root)} exists but no "
                f"{_rel(manifest_path, repo_root)} entry claims it -- an ungated figure. "
                "Re-render, or delete the file if it is a leftover."
            )
    return problems


def _check_entry(
    spec: PlotSpec, entry: object, manifest_path: Path, repo_root: Path
) -> list[str]:
    if not isinstance(entry, dict):
        return [
            f"{_rel(manifest_path, repo_root)}: entry for {spec.key!r} is not an object."
        ]
    problems: list[str] = []

    if entry.get("file") != spec.rel_output:
        problems.append(
            f"{spec.key}: manifest records file {entry.get('file')!r} but "
            f"{SCRIPT_REL} renders {spec.rel_output!r} -- re-render."
        )
    output = repo_root / spec.rel_output
    if not output.is_file():
        problems.append(
            f"{spec.key}: {spec.rel_output} is named in "
            f"{_rel(manifest_path, repo_root)} but does not exist -- re-render, or "
            "restore the committed figure."
        )
    else:
        actual = sha256_bytes_file(output)
        if entry.get("output_sha256") != actual:
            problems.append(
                f"{spec.rel_output} has been edited since it was rendered "
                f"(manifest records {_short(entry.get('output_sha256'))}, file is "
                f"{_short(actual)}) -- a figure is generated, never hand-edited; re-render."
            )

    recorded_inputs = entry.get("inputs")
    if not isinstance(recorded_inputs, dict):
        return problems + [f"{spec.key}: manifest entry has no `inputs` object."]
    for rel in spec.inputs:
        if rel not in recorded_inputs:
            problems.append(
                f"{spec.key}: {SCRIPT_REL} now reads {rel} but the manifest does not "
                "record its hash -- re-render."
            )
    for rel in sorted(set(recorded_inputs) - set(spec.inputs)):
        problems.append(
            f"{spec.key}: the manifest records an input {rel} that {SCRIPT_REL} no "
            "longer reads -- re-render."
        )
    for rel in sorted(set(recorded_inputs) & set(spec.inputs)):
        path = repo_root / rel
        if not path.is_file():
            problems.append(
                f"{spec.key}: cited evidence input {rel} no longer exists -- the figure "
                "is drawn from a file that is gone."
            )
            continue
        actual = sha256_bytes_file(path)
        if recorded_inputs[rel] != actual:
            problems.append(
                f"{spec.key}: evidence input {rel} changed since {spec.rel_output} was "
                f"rendered (manifest records {_short(recorded_inputs[rel])}, file is "
                f"{_short(actual)}) -- the committed figure no longer summarizes it; "
                "re-render."
            )
    return problems


def provenance_problems(specs: tuple[PlotSpec, ...] = PLOTS) -> list[str]:
    """Run every loader and spec-row lookup, reporting failures as text.

    A loader raising `ProvenanceError` means a record's own stated number is
    no longer reproducible from the committed artifact the figure is drawn
    from -- a staleness the hashes cannot see when both files moved together.
    A superseded source record is the same class of rot: the figure would go
    on showing a result a later record has replaced.
    """
    problems: list[str] = []
    for spec in specs:
        try:
            spec_row_label(spec.spec_row)
        except KeyError as exc:
            problems.append(f"{spec.key}: {exc}")
        source = REPO_ROOT / spec.source_record
        if not source.is_file():
            problems.append(f"{spec.key}: source record {spec.source_record} does not exist.")
            continue
        superseder = _superseding_sibling(source)
        if superseder is not None:
            problems.append(
                f"{spec.key}: source record {spec.source_record} has been superseded by "
                f"{_rel(superseder, REPO_ROOT)} -- re-point the figure at the superseding "
                "record and re-render, so it cannot keep showing a replaced result."
            )
        try:
            LOADERS[spec.key]()
        except (ProvenanceError, KeyError, ValueError, OSError) as exc:
            problems.append(f"{spec.key}: {exc}")
    return problems


def _superseding_sibling(record_path: Path) -> Path | None:
    """Another record in the same `records/` directory whose own `Supersedes`
    field names this one -- `sim/README.md`'s append-only convention read the
    way a citation needs it, exactly as `sim/report/generate.py` reads it."""
    this_id = _record_field(record_path, "Record ID") or record_path.stem
    for sibling in sorted(record_path.parent.glob("*.md")):
        if sibling == record_path:
            continue
        value = _record_field(sibling, "Supersedes")
        if value and this_id in value:
            return sibling
    return None


def _rel(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _short(digest: object) -> str:
    return f"{digest[:12]}…" if isinstance(digest, str) and len(digest) > 12 else repr(digest)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def describe() -> str:
    lines = [
        f"{len(PLOTS)} summary plot(s), rendered into docs/plots/ by "
        f"`python3 {SCRIPT_REL} --render`:",
        "",
    ]
    for spec in PLOTS:
        lines.append(f"  {spec.rel_output}")
        lines.append(f"      shows:  {spec.what}")
        lines.append(f"      row:    {spec.spec_row}")
        lines.append(f"      record: {spec.source_record}")
        for rel in spec.extra_inputs:
            lines.append(f"      reads:  {rel}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render and gate the summary plots under docs/plots/ (issue #835). "
            "--check is stdlib-only; --render needs the matplotlib pin in "
            "sim/report/plots-requirements.txt."
        )
    )
    parser.add_argument(
        "--render", action="store_true", help="(re)write docs/plots/*.svg and manifest.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="staleness + provenance gate only (CI mode): exit non-zero without writing",
    )
    parser.add_argument(
        "--list", action="store_true", help="print what is plotted, and from what, then exit"
    )
    args = parser.parse_args(argv)

    if args.list:
        print(describe())
        return 0

    if args.render:
        document = render_all()
        for key, entry in document["plots"].items():
            print(f"wrote {entry['file']}  ({key})")
        print(f"wrote {MANIFEST_REL}")
        remaining = check()
        if remaining:
            print("\nthe freshly-rendered plots do NOT pass --check:", file=sys.stderr)
            for problem in remaining:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        return 0

    problems = check()
    if problems:
        print("STALE PLOTS:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            f"\nRe-render with the pinned dependency, then commit the result:\n"
            f"    python3 -m venv .venv-plots\n"
            f"    .venv-plots/bin/pip install -r sim/report/plots-requirements.txt\n"
            f"    .venv-plots/bin/python {SCRIPT_REL} --render",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print(f"OK: {len(PLOTS)} summary plot(s) in docs/plots/ are fresh against their "
              f"committed evidence, {SCRIPT_REL}, and each record's own stated values.")
    else:
        print(describe())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

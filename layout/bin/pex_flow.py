#!/usr/bin/env python3
"""Shared machinery for the per-block `klt pex` comparison flows (issue #1017).

`layout/comparator/pex/run_pex.py` (issue #112) established the repo's
one-block-one-flow pattern: read `reports/LATEST`, `klt extract --parasitics`
for the per-net R/C table, one `klt pex` call for the schematic-vs-extracted
delta, mint an append-only record. Issues #1016/#1017 add the same flow for
two more blocks (cdac-array, sampling-frontend) and re-mint the comparator's
on the current layout at the ratified corner set -- and the parts of that
machinery that are NOT block-specific (the pinned-`klt` invocation with its
fleet-capacity policy, the ratified one-at-a-time corner carve, the DUT-wrap
convention against `klt extract`'s own `.SUBCKT` header, corner-id parsing,
delta indexing) are exactly the parts that would drift if each flow carried
its own copy -- the same drift argument `sim/harness/klt_sim.py` (issue #865)
centralized for the sim campaigns. This module is that shared half; each
block's `pex/run_pex.py` keeps its own testbenches, analysis and record
prose.

Design decisions this module encodes (each cited where it is enforced):

- **Pinned `klt`.** Every invocation goes through `layout/.venv/bin/klt`
  (layout/requirements.txt's pin, issue #734) -- never the ambient `klt` on
  $PATH, which on a dispatch host is a fleet-managed dev build. Override for
  a throwaway-venv run (issue #1017 step 4) with $PEX_KLT_BIN.
- **Fleet-capacity policy.** `klt pex --backend batch` submits both legs'
  `klt sim` calls to the Spot fleet. The pinned 0.6.0 predates
  `--wait-for-capacity` (the launch script carries its own bounded
  capacity retry), so this module adds the same bounded client-side retry
  `sim/harness/klt_sim.py` gives every batch campaign: a capacity refusal
  is "not right now", never "the block failed".
- **Ratified OAT corner carve.** The request carries the full axis lists and
  an `exclude[]` that removes every cross-product point the ratified
  one-at-a-time star (sim/harness/corners.py, spec/target-spec.md "Numeric
  rows -- RATIFIED 2026-08-19") does not contain -- the same shape
  sim/top-plate-cpar/run_top_plate_cpar.py builds. Supply-tracking sources
  (VREFP=V_DD rail, VCM=VDD/2, input common mode) are carried as *paired*
  `corners.supply_v` keys so a supply corner moves every tracked source
  together, never independently.
- **DUT wrap against the extraction's own header.** The schematic leg's
  `.SUBCKT` wrapper is generated with the *extracted* netlist's own name and
  pin order (parsed from this run's `klt extract` output), so the
  testbench's positional instantiation line means the same thing on both
  legs -- and a pin-list drift fails loudly here instead of silently
  permuting nets.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "sim"

# sim/harness on sys.path, the same way layout/comparator/pex/run_pex.py
# does it (harness.pdk resolution, harness.evidence record ids, and the
# capacity-refusal vocabulary from harness.klt_sim).
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from harness import corners as corners_mod  # noqa: E402
from harness import klt_sim, pdk  # noqa: E402

#: The layout flow's pinned `klt` (layout/requirements.txt, issue #734).
#: $PEX_KLT_BIN overrides it for a throwaway-venv run (issue #1017 step 4).
def klt_bin() -> Path:
    override = os.environ.get("PEX_KLT_BIN")
    if override:
        return Path(override)
    return REPO_ROOT / "layout" / ".venv" / "bin" / "klt"


#: Bounded client-side retry when a `--backend batch` submit is refused for
#: fleet capacity (CLAUDE.md host rule: pass `--wait-for-capacity 600` on
#: every batch submit; the pinned klt 0.6.0 predates that flag, so the wait
#: lives here). One retry per CAPACITY_RETRY_WAIT_S, up to the budget.
#: $PEX_CAPACITY_RETRY_BUDGET_S bounds a single invocation's wait (e.g. a
#: foreground call with its own wall-clock cap); the default matches the
#: host rule's 600 s capacity wait with backoff headroom.
CAPACITY_RETRY_WAIT_S = 120.0
CAPACITY_RETRY_BUDGET_S = float(os.environ.get("PEX_CAPACITY_RETRY_BUDGET_S", "1800"))

#: The quota-phrased refusal `klt pex`'s nested error envelope surfaces --
#: the fleet's shared-spot-budget "exceeds BATCH_MAX_VCPU" launch failure
#: (exit 75) -- which harness.klt_sim's own marker list (built from klt
#: sim's `batch_no_capacity` shapes) does not name. Same "not right now"
#: semantics, so the same retry.
_QUOTA_REFUSAL_MARKERS = (
    "batch_no_capacity",
    "batch_max_concurrent_instances",
    "batch_max_vcpu",
    "batch-fleet-provision.sh launch failed",
    "spot quota is shared",
)


def _is_capacity_refusal(text: str) -> bool:
    lowered = text.lower()
    return klt_sim.is_capacity_refusal(text) or any(
        m in lowered for m in _QUOTA_REFUSAL_MARKERS
    )


class PexFlowError(RuntimeError):
    """A `klt` invocation failed, or an assumption this module enforces
    (pin order, LATEST layout, request shape) does not hold."""


def run_klt(
    args: Sequence[str],
    cwd: Path,
    *,
    backend: str | None = None,
    quiet: bool = False,
) -> dict:
    """Run `<pinned klt> <args> --format json` in `cwd`, decode the JSON
    envelope, and retry a batch-capacity refusal instead of failing.

    Fleet-capacity policy: with `backend="batch"`, a refusal
    (`batch_no_capacity` / concurrency cap) is waited out up to
    CAPACITY_RETRY_BUDGET_S, mirroring what `--wait-for-capacity` (absent on
    the pinned 0.6.0) does on newer clients and what sim/harness/klt_sim.py
    does for every sim campaign. Any other failure raises PexFlowError with
    the tail of the client's output quoted.
    """
    argv = [str(klt_bin()), *args, "--format", "json"]
    deadline = time.monotonic() + CAPACITY_RETRY_BUDGET_S
    attempt = 0
    while True:
        attempt += 1
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(cwd))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            text = proc.stdout + proc.stderr
            envelope = klt_sim.envelope_from_stderr(text)
            if backend == "batch" and (
                (envelope is not None and _is_capacity_refusal(json.dumps(envelope)))
                or _is_capacity_refusal(text)
            ):
                if time.monotonic() < deadline:
                    if not quiet:
                        print(
                            f"  fleet capacity refusal (attempt {attempt}); "
                            f"retrying in {CAPACITY_RETRY_WAIT_S:g}s"
                        )
                    time.sleep(CAPACITY_RETRY_WAIT_S)
                    continue
                raise PexFlowError(
                    "batch submit still refused for capacity after "
                    f"{CAPACITY_RETRY_BUDGET_S:g}s: {klt_sim.error_excerpt(text)}"
                ) from None
            raise PexFlowError(
                f"klt {' '.join(shlex.quote(a) for a in args[:2])} failed "
                f"(exit {proc.returncode}):\n{klt_sim.error_excerpt(text)}"
            ) from None
        # A decoded payload can still BE the refusal: `klt pex` wraps a
        # capacity-failed internal submit as a per-row error object inside
        # an otherwise well-formed JSON response (schematic side may have
        # already run), so the same "not right now" retry applies.
        if (
            backend == "batch"
            and isinstance(payload, dict)
            and payload.get("status") == "error"
            and _is_capacity_refusal(json.dumps(payload))
        ):
            if time.monotonic() < deadline:
                if not quiet:
                    print(
                        f"  fleet capacity refusal inside klt response "
                        f"(attempt {attempt}); retrying in {CAPACITY_RETRY_WAIT_S:g}s"
                    )
                time.sleep(CAPACITY_RETRY_WAIT_S)
                continue
            raise PexFlowError(
                "batch submit still refused for capacity after "
                f"{CAPACITY_RETRY_BUDGET_S:g}s (refusal carried inside the klt "
                f"JSON response): {klt_sim.error_excerpt(json.dumps(payload))}"
            ) from None
        return payload


def resolve_pdk() -> pdk.PdkInfo:
    info = pdk.resolve()
    if not info.found:
        raise PexFlowError(f"PDK not resolvable: {info.error}")
    return info


def latest_layout(block_dir: Path, gds_name: str) -> tuple[Path, str]:
    """(absolute GDS path, LATEST record id) for a layout/<block>/ directory.

    The pex flow only ever READS `reports/LATEST` -- that pointer belongs to
    the drawing flow (layout/comparator/pex/README.md's convention).
    """
    latest = (block_dir / "reports" / "LATEST").read_text().strip()
    gds = block_dir / "reports" / latest / gds_name
    if not gds.is_file():
        raise PexFlowError(f"no {gds_name} under reports/{latest}/ for {block_dir.name}")
    return gds, latest


def extract_parasitics(
    gds_path: Path, out_dir: Path, spice_name: str, info: pdk.PdkInfo, *, quiet: bool = False
) -> dict:
    """`klt extract --parasitics` into `out_dir/spice_name`; returns the JSON
    envelope (also written to out_dir/extract.json by the caller if wanted).

    The GDS path is passed ABSOLUTE: `klt` path-scopes echoed paths back to
    repo-relative itself, and a relative path computed against a scratch
    working directory (the pilot runs from /tmp) resolves from `klt`'s own
    cwd chain instead -- the same class of relative-path mismatch its
    absolute `-o` convention exists to avoid (klayout-tools#1525).
    """
    payload = run_klt(
        [
            "extract",
            str(gds_path.resolve()),
            "--deck",
            "sky130",
            "--pdk",
            info.variant,
            "--pdk-root",
            str(info.root),
            "--parasitics",
            "-o",
            spice_name,
        ],
        cwd=out_dir,
        quiet=quiet,
    )
    if payload.get("status") != "extracted":
        raise PexFlowError(f"klt extract failed: {json.dumps(payload)[:600]}")
    if not quiet:
        print(
            f"  klt extract --parasitics: {payload['status']} "
            f"({payload['device_count']} devices, {payload['net_count']} nets)"
        )
    return payload


_SUBCKT_RE = re.compile(r"^\.SUBCKT\s+(\S+)((?:\s+\S+)+)\s*$", re.IGNORECASE)


def extracted_subckt(spice_path: Path) -> tuple[str, list[str]]:
    """(name, pins) from an extracted netlist's top `.SUBCKT` header, joining
    its `+` continuation lines (klt extract wraps long pin lists)."""
    body: list[str] = []
    for line in spice_path.read_text().splitlines():
        stripped = line.strip()
        if not body:
            if _SUBCKT_RE.match(stripped):
                body.append(stripped)
        elif stripped.startswith("+"):
            body.append(stripped[1:].strip())
        elif body:
            break
    if not body:
        raise PexFlowError(f"no .SUBCKT header found in {spice_path}")
    m = _SUBCKT_RE.match(body[0])
    pins = m.group(2).split() + " ".join(body[1:]).split()
    return m.group(1), pins


def wrap_dut(fragment: str, subckt_name: str, pins: list[str], header: str) -> str:
    """Wrap a flat, simulable device fragment in `.SUBCKT <name> <pins>`.

    `fragment` is the schematic side's own netlist text (sky130_fd_pr__
    device cards -- NOT the LVS reference's generic `nfet`/`pfet` classes,
    which name no ngspice model); `pins` is the EXTRACTED netlist's own pin
    list so both legs' positional instantiations mean the same thing.
    """
    pins_line = " ".join(pins)
    if len(pins_line) > 200:  # keep decks readable: wrap like klt extract does
        rows = [pins[i : i + 12] for i in range(0, len(pins), 12)]
        pins_line = "\n+ ".join(" ".join(r) for r in rows)
    return f"{header}\n.SUBCKT {subckt_name} {pins_line}\n{fragment}\n.ENDS {subckt_name}\n"


# ---------------------------------------------------------------------------
# Ratified one-at-a-time corner carve (sim/harness/corners.py's grid, expressed
# in a `klt sim`/`klt pex` request's corners + exclude fields).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OatPoint:
    process: str
    temp_c: float
    supply_v: float
    # supply-tracking sources, keyed by their `corners.supply_v` source name:
    # e.g. {"vrefp": 1.8, "vcm": 0.9}. Always includes the rail under "vdd".
    supply_sources: dict[str, float] = field(default_factory=dict)

    @property
    def cid(self) -> str:
        return corners_mod.corner_id(self.process, self.temp_c, self.supply_v)


def ratified_oat_points(
    paired_sources: dict[str, Callable[[float], float]],
    *,
    nominal_v: float = 1.8,
    tolerance: float = corners_mod.RATIFIED_SUPPLY_TOLERANCE,
    process_corners: Sequence[str] = corners_mod.RATIFIED_PROCESS_CORNERS,
    temps_c: Sequence[float] = corners_mod.RATIFIED_TEMPS_C,
) -> list[OatPoint]:
    """The ratified 9-point OAT star as `klt sim` request corner points.

    `paired_sources` maps each supply-tracking source name to its
    value-as-a-function-of-rail (the rail itself is always added under
    "vdd"): `{"vcm": lambda v: v / 2}` makes every VCM point track its
    corner's rail, so a supply corner moves the tracked sources together
    rather than crossing them independently.
    """
    sources = {"vdd": lambda v: v}
    sources.update(paired_sources)
    return [
        OatPoint(p, t, v, {name: fn(v) for name, fn in sources.items()})
        for p, t, v in corners_mod.ratified_oat_grid(nominal_v, tolerance, list(process_corners), list(temps_c))
    ]


def build_corners_spec(points: Sequence[OatPoint]) -> tuple[dict, list[dict]]:
    """(corners, exclude) fields carving exactly `points` out of the request's
    corner cross-product -- the shape sim/top-plate-cpar's request builder
    established. `exclude` removes every cross-product point the OAT star
    does not contain (paired sources make independent combinations, so the
    carve is what keeps e.g. VCM=0.9 from pairing with VDD=1.62)."""
    supply_keys = sorted({k for pt in points for k in pt.supply_sources})
    corners = {
        "process": sorted({pt.process for pt in points}),
        "supply_v": {k: sorted({pt.supply_sources[k] for pt in points}) for k in supply_keys},
        "temperature_c": sorted({pt.temp_c for pt in points}),
    }
    want = {
        (pt.process, pt.temp_c, tuple(sorted(pt.supply_sources.items()))) for pt in points
    }
    exclude: list[dict] = []
    for p in corners["process"]:
        for t in corners["temperature_c"]:
            for combo in _cross(corners["supply_v"]):
                key = (p, t, combo)
                if key not in want:
                    exclude.append(
                        {"process": p, "temperature_c": t, "supply_v": dict(combo)}
                    )
    return corners, exclude


def _cross(supply_v: dict[str, list[float]]) -> list[tuple[tuple[str, float], ...]]:
    keys = sorted(supply_v)
    out: list[tuple[tuple[str, float], ...]] = [()]
    for k in keys:
        out = [row + ((k, v),) for row in out for v in supply_v[k]]
    return out


_DECIMAL = r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_CORNER_ID_RE = re.compile(
    rf"(?P<process>[a-z]+[a-z0-9]*)/(?P<supplies>[^/]+)V/(?P<temp>{_DECIMAL})C"
)
_SUPPLY_TOKEN_RE = re.compile(rf"([A-Za-z0-9]+)=({_DECIMAL})")


def parse_corner_id(cid: str) -> tuple[str, float, dict[str, float]]:
    """(process, temp_c, {source: volts}) from a `klt sim` corner id such as
    ``tt/1.800V/27C`` or ``tt/vdd=1.800_vcm=0.900V/27C``. The single
    unnamed source in these flows is the rail added by ratified_oat_points."""
    m = _CORNER_ID_RE.fullmatch(cid)
    if not m:
        raise PexFlowError(f"unparseable corner id {cid!r}")
    field = m.group("supplies")
    if "=" not in field:
        field = "vdd=" + field
    supplies = {}
    for token in field.split("_"):
        match = _SUPPLY_TOKEN_RE.fullmatch(token)
        if not match or match.group(1) in supplies:
            raise PexFlowError(f"unparseable supply in corner id {cid!r}")
        supplies[match.group(1)] = float(match.group(2))
    return m.group("process"), float(m.group("temp")), supplies


def delta_index(pex_json: dict) -> dict[str, dict[str, dict[str, float | None]]]:
    """pex `delta[]` -> {corner_id: {spec_row:
    {"schematic": v, "extracted": v, "delta_pct": d, "status": s}}}."""
    out: dict[str, dict[str, dict[str, float | None]]] = {}
    for row in pex_json.get("delta", []):
        out.setdefault(row["corner_id"], {})[row["spec_row"]] = {
            "schematic": row.get("schematic_value"),
            "extracted": row.get("extracted_value"),
            "delta_pct": row.get("delta_pct"),
            "status": row.get("status"),
        }
    return out


def net_table(extract_json: dict, wanted: set[str]) -> dict[str, dict[str, float]]:
    """{net: {r_ohm, c_ground_ff, c_coupled_total_ff, c_total_ff}} for the
    nets in `wanted`, from `klt extract --parasitics`'s per-net table."""
    out: dict[str, dict[str, float]] = {}
    for net in extract_json.get("parasitics", {}).get("nets", []):
        name = net["net"].lstrip("\\").replace("\\", "")
        if name in wanted:
            coupled = sum(c["capacitance_ff"] for c in net.get("coupled", []))
            out[name] = {
                "r_ohm": net["resistance_ohm"],
                "c_ground_ff": net["capacitance_ff"],
                "c_coupled_total_ff": coupled,
                "c_total_ff": net["capacitance_ff"] + coupled,
            }
    return out


def pinned_klt_version() -> str | None:
    """The klayout-tools version layout/requirements.txt pins, or None."""
    req = REPO_ROOT / "layout" / "requirements.txt"
    m = re.search(r"^klayout-tools==(\S+)\s*$", req.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def klt_version_note(version: str) -> str:
    """Report the run's klt version and the recorded reason for the #1017 substitution."""
    pin = pinned_klt_version()
    if pin and version != pin:
        note = f"`klt` version: **{version}** (layout/requirements.txt pins {pin})."
        if (pin, version) == ("0.6.0", "0.9.0"):
            note += (
                " For the November 2026 records, the builder reported errors at every "
                "corner on the first batch attempt, attributed them to a client/runner "
                "version mismatch, and switched to a throwaway venv under issue #1017 "
                "step 4. Only the successful run's envelopes are archived here."
            )
        return note
    return f"`klt` version: {version} (layout/requirements.txt pin)"


def apply_capacity_wait(request: dict) -> dict:
    """Add `batch.capacity_wait_s` to a request when $PEX_CAPACITY_WAIT_S is
    set -- the host rule's `--wait-for-capacity` expressed request-side
    (issue #2721), which `klt pex`'s internal `klt sim` calls then inherit
    per submit. Off by default so local single-corner pilots on the pinned
    0.6.0 (whose request loader predates the key) stay runnable; record
    invocations set it."""
    wait = os.environ.get("PEX_CAPACITY_WAIT_S")
    if wait:
        request = dict(request)
        request["batch"] = {**(request.get("batch") or {}), "capacity_wait_s": float(wait)}
    return request

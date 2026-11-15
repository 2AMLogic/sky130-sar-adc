"""The one `evidence.resolve_provenance` stub for the PDK-free record-writer
tests (issue #914).

Every `sim/*/run_*.py` record writer calls
`harness.evidence.resolve_provenance()` to mint a record id, snapshot the
netlist and read the PDK/ngspice provenance line. Only the *reading* part
needs a real PDK and a real ngspice, so the record-writer unit tests stub the
whole function out and redirect the campaign module's `EXPERIMENT_DIR` into a
temp dir -- which is how the whole `sim/tests/` suite runs with neither tool
installed (`sim/tests/test_harness.py`'s PDK-free convention).

Before this module that stub was copied inline at thirteen sites across five
files, each with its own hand-written save/restore pair, and the copies had
already drifted on the one constant nothing asserted on
(`ng_version`: twelve `ngspice-46`, one `ngspice-47`). This is the test-side
counterpart of the driver-side consolidation `sim/README.md` records for the
`klt sim` submit path, and `sim/tests/test_provenance_fixture.py`'s structural
guard holds it the same way that one is held: it fails if a test file grows
its own copy again.

Two shapes, matching the two the suite had already reached for independently:

- `make_fake_resolve()` -- the bare replacement function, for a caller that
  installs it itself (`test_harness.py` patches `resolve_provenance` with no
  campaign module to redirect).
- `fake_provenance(module, tmp_dir)` -- the context manager, for the common
  case: patch `<module>.EXPERIMENT_DIR` and `evidence.resolve_provenance`
  together for the duration of a `with` block.

Both install via `unittest.mock.patch.object`, so the restore is the context
manager's job rather than a `try:`/`finally:` pair re-typed at each site.

The stub delegates its filesystem side effects to the *real*
`evidence.write_netlist_snapshot_text()` -- the helper the production
`resolve_provenance()` itself calls, and the thing the thirteen copies were
each re-implementing by hand. So the directories it creates, the snapshot it
writes and the `records/<record-id>.md` path it returns are production
behaviour, not a second guess at it; only the four values that need a
toolchain to resolve (`record_id`, `netlist_sha`, `pdk_line`, `ng_version`)
are faked.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR))

from harness import evidence  # noqa: E402

#: The fixed record id every stubbed writer mints. Tests assert on
#: `records/REC.md`, `corners/REC/` and `diagnostics/REC/` by name, so this is
#: deliberately a constant rather than `evidence.new_record_id()`'s timestamp.
RECORD_ID = "REC"

#: A sha-shaped placeholder: the writers only ever render it.
NETLIST_SHA = "0" * 64

#: Stands in for `pdk.resolve()`, which needs a PDK checkout.
PDK_LINE = "sky130A @ testing"

#: Stands in for `toolchain._ngspice_version()`, which needs ngspice on PATH.
#:
#: `ngspice-46` is the suite-wide default: twelve of the thirteen consolidated
#: copies used it, and `sim/tests/test_harness.py` asserts on it directly, so
#: that assertion now pins this constant. The thirteenth
#: (`test_solver_policy.py`) returned `ngspice-47`; nothing asserted on it
#: there and nothing branches on it in the writer it drove -- the solver-audit
#: record only renders the version into a prose comparison -- so it was
#: undocumented drift and is reconciled onto this default. A test that
#: genuinely needs a different version passes `ng_version=` and says why.
NG_VERSION = "ngspice-46"


def make_fake_resolve(
    *,
    record_id: str = RECORD_ID,
    netlist_sha: str = NETLIST_SHA,
    pdk_line: str = PDK_LINE,
    ng_version: str = NG_VERSION,
    seen: list[str] | None = None,
) -> Callable[[Path, str], evidence.ProvenanceInfo]:
    """Build a drop-in replacement for `evidence.resolve_provenance()`.

    The returned function performs the real helper's filesystem work under
    whatever `experiment_dir` the writer hands it -- create
    `netlist-snapshots/` and `records/`, write
    `netlist-snapshots/<record_id>.spice`, return `records/<record_id>.md` --
    and reports the four toolchain-resolved fields as the constants above.

    Pass `seen` to collect each `netlist_text` the writer snapshots, in call
    order; that is how `test_harness.py` checks *which* corner's deck
    `resolve_corners_provenance()` chose to snapshot.
    """

    def fake_resolve(experiment_dir: Path, netlist_text: str) -> evidence.ProvenanceInfo:
        if seen is not None:
            seen.append(netlist_text)
        record_path = evidence.write_netlist_snapshot_text(
            experiment_dir, record_id, netlist_text
        )
        return evidence.ProvenanceInfo(
            record_id=record_id,
            record_path=record_path,
            netlist_sha=netlist_sha,
            pdk_line=pdk_line,
            ng_version=ng_version,
        )

    return fake_resolve


@contextlib.contextmanager
def fake_provenance(
    module: Any,
    experiment_dir: Path,
    **kwargs: Any,
) -> Iterator[Callable[[Path, str], evidence.ProvenanceInfo]]:
    """Redirect `module.EXPERIMENT_DIR` at `experiment_dir` and stub
    `evidence.resolve_provenance()`, for the body of a `with` block.

    `module` is the campaign module whose `EXPERIMENT_DIR` the writer under
    test reads -- the only thing that varies between the call sites (e.g.
    `full_conversion_campaigns.common`,
    `supply_impedance_campaigns.common`, `run_vcm_drive_budget`). `kwargs`
    are forwarded to `make_fake_resolve()`.

    Yields the stub, so a caller wanting the `seen` list can also reach the
    function it installed. Both patches are reverted on exit, including on an
    exception -- the property the thirteen hand-written `try:`/`finally:`
    pairs each had to re-establish, and which
    `test_run_vcm_drive_budget.py`'s "no path under the real experiment dir is
    written" tests check from the outside.
    """
    fake = make_fake_resolve(**kwargs)
    with mock.patch.object(module, "EXPERIMENT_DIR", Path(experiment_dir)), \
            mock.patch.object(evidence, "resolve_provenance", fake):
        yield fake

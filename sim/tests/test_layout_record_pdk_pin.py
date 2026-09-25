"""Unit tests for `layout/bin/_record_common.py`'s `resolve_pdk_commit` --
pure stdlib, no real `klt`/PDK install required (a fake `klt` shell script
stands in for it, same PDK-free unit-test convention as
sim/tests/test_drc_evidence.py and sim/tests/test_proposal_citations.py; see
sim/selftest.sh stage 1/4).

These live under sim/tests/ because that is this repo's only unittest root
(`npm run test:unit` discovers from there), not because this helper belongs to
the simulation harness -- it renders `layout/` evidence.

Issue #407: `layout/sar-adc-top/bin/render-record.py` and
`layout/cdac-array/bin/render-record.py` (and, transitively via
`render_pnr_drc_lvs_record`, `layout/sar-sequencer/` and
`layout/seln-inverters/`) printed only the PDK *variant name* (e.g.
`sky130A`) in their record's Provenance section -- which corner of the PDK a
flow asked for, not which install (i.e. which upstream `open_pdks` commit)
answered that ask. The load-bearing tests below reproduce that defect shape
directly against `resolve_pdk_commit`, and cross-check the fixed renderer
output against `docs/chipalooza/check_proposal_citations.py`'s own
`_names_pdk_commit` predicate -- the census check (check 26) that a
`- PDK variant: sky130A`-only line fails to satisfy -- so a future refactor
that silently drops the commit back out of a renderer's Provenance section is
caught here rather than only by that document-level check.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_DIR.parent
LAYOUT_BIN = REPO_ROOT / "layout" / "bin"
sys.path.insert(0, str(LAYOUT_BIN))
sys.path.insert(0, str(REPO_ROOT / "docs" / "chipalooza"))

import _record_common as record_common  # noqa: E402
import check_proposal_citations as citations  # noqa: E402

OPEN_PDKS_COMMIT = "open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b"


def _fake_klt(tmp_dir: str, *, stdout: str = "", exit_code: int = 0) -> str:
    """Write an executable stand-in for `klt` under *tmp_dir* whose `pdk find`
    subcommand prints *stdout* verbatim and exits *exit_code*; any other
    invocation (e.g. `--version`) just exits 0 with no output."""
    path = Path(tmp_dir) / "fake-klt"
    path.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1 $2\" == \"pdk find\" ]]; then\n"
        f"  cat <<'PDKEOF'\n{stdout}\nPDKEOF\n"
        f"  exit {exit_code}\n"
        "fi\n"
        "exit 0\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class TestResolvePdkCommit(unittest.TestCase):
    def test_resolves_the_version_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout=json.dumps({"version": OPEN_PDKS_COMMIT}))
            self.assertEqual(
                record_common.resolve_pdk_commit(klt, "sky130A"), OPEN_PDKS_COMMIT
            )

    def test_degrades_on_missing_klt(self):
        self.assertEqual(
            record_common.resolve_pdk_commit(
                "/no/such/klt-binary", "sky130A"
            ),
            "(unresolvable)",
        )

    def test_degrades_on_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout="not json at all")
            self.assertEqual(
                record_common.resolve_pdk_commit(klt, "sky130A"), "(unresolvable)"
            )

    def test_degrades_on_a_failed_resolution(self):
        """`klt pdk find` on no resolvable install still prints a JSON error
        envelope with no top-level `version` field (see `klt pdk find --help`)
        -- must not be mistaken for a resolved commit."""
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(
                tmp,
                stdout=json.dumps({"error": {"message": "no PDK install found"}}),
                exit_code=1,
            )
            self.assertEqual(
                record_common.resolve_pdk_commit(klt, "sky130A"), "(unresolvable)"
            )

    def test_degrades_on_a_null_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout=json.dumps({"version": None}))
            self.assertEqual(
                record_common.resolve_pdk_commit(klt, "sky130A"), "(unresolvable)"
            )


class TestRenderPnrDrcLvsRecordNamesThePdkCommit(unittest.TestCase):
    """`render_pnr_drc_lvs_record` (shared by layout/sar-sequencer/ and
    layout/seln-inverters/'s own render-record.py scripts) is the one place
    in `_record_common.py` this issue's own "suggested fix" names by line
    number -- assert its Provenance section actually satisfies the census
    checker's own `_names_pdk_commit` predicate, not just that it contains
    *a* string with "PDK" in it.
    """

    def _render(self, klt: str) -> str:
        with tempfile.TemporaryDirectory() as out_dir, tempfile.TemporaryDirectory() as repo_root:
            args = record_common.build_argparser().parse_args(
                [
                    "--out-dir", out_dir,
                    "--record-id", "20260101-000000-abc1234",
                    "--repo-root", repo_root,
                    "--klt", klt,
                    "--pdk-variant", "sky130A",
                ]
            )
            return record_common.render_pnr_drc_lvs_record("Test block", args)

    def test_names_the_open_pdks_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout=json.dumps({"version": OPEN_PDKS_COMMIT}))
            body = self._render(klt)
            self.assertIn(OPEN_PDKS_COMMIT, body)
            self.assertTrue(
                citations._names_pdk_commit(body),
                "render_pnr_drc_lvs_record's Provenance section does not "
                "satisfy check 26's own _names_pdk_commit predicate -- "
                "issue #407's regression",
            )

    def test_variant_name_alone_would_not_have_passed(self):
        """Reproduces the exact pre-fix defect shape: a line naming only the
        PDK *variant*, with no 40-hex commit, must NOT satisfy the census
        checker -- otherwise check 26 could not have caught this issue."""
        stale_body = "## Provenance\n- PDK variant: sky130A\n"
        self.assertFalse(citations._names_pdk_commit(stale_body))

    def test_degrades_gracefully_when_klt_cannot_resolve_a_pdk(self):
        body = self._render("/no/such/klt-binary")
        pdk_line = next(line for line in body.splitlines() if line.startswith("- PDK:"))
        self.assertEqual(pdk_line, "- PDK: sky130A ((unresolvable))")


class TestSubBlockRenderersNameThePdkCommit(unittest.TestCase):
    """`layout/sar-adc-top/bin/render-record.py` and
    `layout/cdac-array/bin/render-record.py` build their own Provenance
    section directly (they do not go through `render_pnr_drc_lvs_record`) --
    the other two of the four call sites issue #407 names by line number.
    Run each as a real subprocess (as `run-flow.sh` does) against an empty
    `--out-dir`, which both scripts tolerate (`_record_common.load_json`
    degrades a missing envelope to `{}` rather than raising).
    """

    def _run(self, script: Path, klt: str) -> str:
        with tempfile.TemporaryDirectory() as out_dir:
            proc = subprocess.run(
                [
                    sys.executable, str(script),
                    "--out-dir", out_dir,
                    "--record-id", "20260101-000000-abc1234",
                    "--repo-root", str(REPO_ROOT),
                    "--klt", klt,
                    "--pdk-variant", "sky130A",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return proc.stdout

    def test_sar_adc_top_names_the_open_pdks_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout=json.dumps({"version": OPEN_PDKS_COMMIT}))
            body = self._run(
                REPO_ROOT / "layout" / "sar-adc-top" / "bin" / "render-record.py", klt
            )
            self.assertIn(OPEN_PDKS_COMMIT, body)
            self.assertTrue(citations._names_pdk_commit(body))

    def test_cdac_array_names_the_open_pdks_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            klt = _fake_klt(tmp, stdout=json.dumps({"version": OPEN_PDKS_COMMIT}))
            body = self._run(
                REPO_ROOT / "layout" / "cdac-array" / "bin" / "render-record.py", klt
            )
            self.assertIn(OPEN_PDKS_COMMIT, body)
            self.assertTrue(citations._names_pdk_commit(body))


if __name__ == "__main__":
    unittest.main()

"""Guard the hand-kept "newest record" prose in README.md and docs/ROADMAP.md
against `sim/*/records/LATEST` drift (issue #974).

`README.md` and `docs/ROADMAP.md` each carry a hand-written sentence about the
full-conversion campaign's current evidence. Before PR #973, `docs/ROADMAP.md`
named the record id (`sim/full-conversion-transient/records/
20261011-112119-188e94c.md`) and never named the campaign's `records/LATEST`
pointer, so when an informational record landed there was no mechanical way
to tell that "the newest ... record" had gone stale -- a human reading PR #973
caught it. This module is the mechanical gate, in the shape this repo already
established for hand-kept prose (`sim/tests/test_readme_t1_count.py`,
issue #911); `npm run check:ci` runs no markdown text checker, so a
`sim/tests/` module is the only available gate.

The unit of analysis is the **top-level markdown bullet** (`^- `), not the
document and not the free text. The gate never reads prose: it matches only
machine-shaped path tokens.

For each top-level bullet:

1. Collect the `sim/<campaign>/` names the bullet mentions, via a
   `sim/<campaign>/records/<stamp>.md` or `sim/<campaign>/records/LATEST`
   path token. A stamp inside a `layout/<block>/reports/` or `erc-reports/`
   path is never attributed to a `sim/` campaign (the "Pins and freshness"
   bullet states a deliberate manifest-vs-pointer divergence, #743).
2. Skip any campaign publishing no `records/LATEST` -- nothing to be stale
   against (the same carve-out `docs/citation-gate.md` check 3 records).
3. **Non-vacuity**: a bullet that cites `sim/<campaign>/records/<stamp>.md`
   but never names that campaign's `records/LATEST` fails. This is the rule
   that bites on the real pre-#973 defect.
4. **At-least-one**: once the pointer is named, at least one stamp-shaped
   token in the bullet must equal the pointer's target. Additional stamps are
   legal -- `docs/ROADMAP.md` legitimately cites the #913 boundary-sweep
   record, which moves no pointer (`run_conversion.py` moves the pointer only
   for the corner campaign under the reference solver profile).

Rule 4 is deliberately `docs/citation-gate.md` check 3's shape ("at least one
of that row's cited record stamps must be what the flow's own `LATEST` pointer
resolves to. A row may additionally cite superseded records ... that is not a
defect. Flows with no `LATEST` pointer are skipped").

Per this repo's test convention the gate is proven to **bite on synthetic
fixtures**, not merely to agree with the live tree: a checker that cannot
fail on a moved pointer or a pointerless stamp citation is a vacuous gate.
The live-tree assertion is a separate test (`TestLiveTree`) from the fixture
assertions, and the module is PDK-free and network-free (pure file reads), so
it runs in the headless `checks` job.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

GUARDED_DOCS = ("README.md", "docs/ROADMAP.md")

# A sim record stamp: `<yyyymmdd>-<hhmmss>-<git short sha>.md`, bare or inside
# a path. The id shape is `check_proposal_citations.py`'s own STAMP pattern
# (`\d{8}-\d{6}-[0-9a-f]+` -- the short-sha width is not fixed), extended with
# the `.md` suffix a record citation always carries.
STAMP = r"\d{8}-\d{6}-[0-9a-f]+"
RECORD_STAMP_RE = re.compile(STAMP + r"\.md\b")

# A `sim/<campaign>/records/<stamp>.md` or `sim/<campaign>/records/LATEST`
# path token. This is the only shape that names a campaign.
SIM_RECORD_TOKEN_RE = re.compile(
    r"sim/(?P<campaign>[a-z0-9][a-z0-9-]*)/records/"
    r"(?:LATEST(?![\w-])|" + STAMP + r"\.md\b)"
)

# A `records/LATEST` pointer mention, with or without the `sim/<campaign>/`
# prefix. A bare mention (`records/LATEST`) names the pointer of every
# campaign the bullet mentions.
POINTER_TOKEN_RE = re.compile(
    r"(?:(?P<prefix>sim/[a-z0-9][a-z0-9-]*)/)?records/LATEST(?![\w-])"
)

TOP_LEVEL_BULLET_RE = re.compile(r"^- ", re.MULTILINE)


def split_bullets(text: str) -> list[str]:
    """Split markdown text into top-level (`^- `) bullets.

    A bullet spans from its `^- ` line to just before the next top-level
    bullet, so continuation lines and indented sub-bullets stay with their
    parent. Adjacent top-level bullets never merge; non-bullet text (table
    rows, paragraphs, headings) is not part of any bullet.
    """
    starts = [m.start() for m in TOP_LEVEL_BULLET_RE.finditer(text)]
    bullets = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        bullets.append(text[start:end])
    return bullets


def bullet_campaigns(bullet: str) -> set[str]:
    """Return the `sim/<campaign>/` names the bullet mentions via a
    `sim/<campaign>/records/` path token.

    A stamp inside a `layout/<block>/reports/` or `erc-reports/` path is never
    attributed to a `sim/` campaign: only a `sim/`-anchored token names one.
    """
    return {m.group("campaign") for m in SIM_RECORD_TOKEN_RE.finditer(bullet)}


def bullet_pointer_campaigns(bullet: str, campaigns: set[str]) -> set[str]:
    """Return the subset of ``campaigns`` whose `records/LATEST` the bullet
    names.

    A `sim/<campaign>/records/LATEST` token names that campaign's pointer; a
    bare `records/LATEST` token names the pointer of every campaign the
    bullet mentions.
    """
    named: set[str] = set()
    for m in POINTER_TOKEN_RE.finditer(bullet):
        prefix = m.group("prefix")
        if prefix is not None:
            campaign = prefix.removeprefix("sim/")
            if campaign in campaigns:
                named.add(campaign)
        else:
            named |= campaigns
    return named


def bullet_violations(bullet: str, sim_root: Path) -> list[str]:
    """Return the rule 2-4 violations a single bullet commits against the
    pointers published under ``sim_root`` (the `sim/` directory).

    Returns an empty list for a conforming bullet, for a bullet mentioning no
    `sim/<campaign>/records/` token at all, and for campaigns that publish no
    pointer.
    """
    campaigns = bullet_campaigns(bullet)
    if not campaigns:
        return []
    pointer_named = bullet_pointer_campaigns(bullet, campaigns)
    stamps = set(RECORD_STAMP_RE.findall(bullet))
    violations: list[str] = []
    for campaign in sorted(campaigns):
        pointer_path = sim_root / campaign / "records" / "LATEST"
        if not pointer_path.is_file():
            continue  # rule 2: nothing to be stale against
        target = pointer_path.read_text(encoding="utf-8").strip()
        if campaign not in pointer_named:
            violations.append(
                f"campaign '{campaign}' is cited by record stamp but the "
                "bullet never names its records/LATEST pointer"
            )
        elif target not in stamps:
            violations.append(
                f"campaign '{campaign}' names its records/LATEST pointer "
                f"but no stamp in the bullet equals its target ({target})"
            )
    return violations


def check_text(text: str, sim_root: Path) -> list[str]:
    """Return the violations every top-level bullet of ``text`` commits."""
    violations: list[str] = []
    for bullet in split_bullets(text):
        violations.extend(bullet_violations(bullet, sim_root))
    return violations


def check_repo(repo_root: Path = REPO_ROOT) -> list[str]:
    """Run the gate over the live guarded documents; return [] on pass."""
    sim_root = repo_root / "sim"
    violations: list[str] = []
    for rel in GUARDED_DOCS:
        text = (repo_root / rel).read_text(encoding="utf-8")
        for message in check_text(text, sim_root):
            violations.append(f"{rel}: {message}")
    return violations


def write_pointer(sim_root: Path, campaign: str, target: str) -> None:
    """Mint a synthetic `records/LATEST` pointer for a fixture."""
    directory = sim_root / campaign / "records"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "LATEST").write_text(target + "\n", encoding="utf-8")


# --- Verbatim fixtures -----------------------------------------------------
# The pre-#973 `docs/ROADMAP.md` Conversion bullet: cites the record stamp,
# never names the pointer. Quoted verbatim from `main` @ 259c10f3 (unchanged
# at the time this gate was written); this is the real defect, rule 3.
PRE_973_ROADMAP_BULLET = (
    "- **Conversion: overall FAIL.** The newest full-conversion record\n"
    "  (`sim/full-conversion-transient/records/20261011-112119-188e94c.md`) resolves\n"
    "  3 of 5 inputs within ±1 LSB at each of the nine ratified corners; the two\n"
    "  near-full-scale inputs do not converge. DR-021 proposes the fix and DR-025\n"
    "  the gain-error closure path; neither is ratified or implemented.\n"
)

# PR #973's corrected bullet: names the pointer, quotes the stamp bare, and
# additionally cites the #913 informational boundary sweep, which moves no
# pointer. Quoted verbatim from PR #973's head diff; satisfies rules 3 and 4.
POST_973_ROADMAP_BULLET = (
    "- **Conversion: overall FAIL.** The newest full-conversion **corner-campaign**\n"
    "  record (`sim/full-conversion-transient/records/LATEST`, pointing at\n"
    "  `20261011-112119-188e94c.md`) resolves 3 of 5 inputs within ±1 LSB at each\n"
    "  of the nine ratified corners; the two near-full-scale inputs do not\n"
    "  converge. An informational boundary sweep\n"
    "  (`sim/full-conversion-transient/records/20261115-084232-ad7393c6.md`,\n"
    "  issue #913 — baseline corner `tt_27c_1.80v` only, DC inputs, ideal sources,\n"
    "  no noise; grades no spec row and supersedes nothing) locates where\n"
    "  conversion stops being correct: inputs converge up to `+0.30·V_REF` /\n"
    "  `-0.35·V_REF` and first fail at `+0.35·V_REF` / `-0.40·V_REF`, resolved to\n"
    "  the sweep's `0.05·V_REF` step. DR-021 proposes the fix and DR-025\n"
    "  the gain-error closure path; neither is ratified or implemented.\n"
)

# `README.md`'s Conversion bullet: cites the stamp via a full path and names
# the pointer bare. Quoted verbatim from `README.md` (truncated after the
# sentence that carries the tokens); satisfies rules 3 and 4.
README_CONVERSION_BULLET = (
    "- **Conversion: partial, overall FAIL** — the full-conversion transient\n"
    "  campaign ([`sim/full-conversion-transient/`](sim/full-conversion-transient/README.md);\n"
    "  newest record:\n"
    "  [`records/20261011-112119-188e94c.md`](sim/full-conversion-transient/records/20261011-112119-188e94c.md),\n"
    "  named in `records/LATEST`) resolves the three mid-scale inputs to within\n"
    "  ±1 LSB at all nine ratified corners.\n"
)

# `docs/ROADMAP.md`'s "Pins and freshness" bullet: stamps of layout runs and a
# `layout/sar-adc-top/reports/LATEST` pointer -- none of it a `sim/` campaign.
# Quoted verbatim from `docs/ROADMAP.md`; must never be flagged (#743).
ROADMAP_PINS_BULLET = (
    "- **Pins and freshness.** `layout/requirements.txt` is `klayout-tools==0.6.0`;\n"
    "  the grader in `signoff/requirements.txt` is `0.8.0`. `sim/pdk.json` pins\n"
    "  open_pdks `f6eeac7`, superseding `c6d73a3`. The manifest cites top-level run\n"
    "  `20261001-211249-1ca34e6` for items 3, 4 and 11, while\n"
    "  `layout/sar-adc-top/reports/LATEST` is `20261027-193335-4433671f` (#743).\n"
)

CURRENT_RECORD_STAMP = "20261011-112119-188e94c.md"
# The #913 informational boundary sweep: a real record that correctly moves no
# pointer (`run_conversion.py` moves the pointer only for the corner campaign
# under the reference solver profile).
BOUNDARY_SWEEP_STAMP = "20261115-084232-ad7393c6.md"


class FixtureCase(unittest.TestCase):
    """Base class that runs the gate against a synthetic `sim/` tree."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        self.sim_root = self.repo / "sim"
        self.sim_root.mkdir()

    def assertBulletPasses(self, bullet: str) -> None:
        self.assertEqual(
            bullet_violations(bullet, self.sim_root),
            [],
            "conforming bullet reported a violation",
        )

    def assertBulletFails(self, bullet: str, fragment: str) -> None:
        violations = bullet_violations(bullet, self.sim_root)
        self.assertTrue(
            violations,
            "defective bullet passed the gate; the checker is vacuous",
        )
        self.assertTrue(
            any(fragment in v for v in violations),
            f"no violation names the expected defect ({fragment!r}); got "
            f"{violations!r}",
        )


class TestBulletParser(unittest.TestCase):
    """Rule 0: the parser's unit of analysis is the top-level bullet."""

    def test_adjacent_top_level_bullets_do_not_merge(self) -> None:
        # The Conversion bullet must not absorb "Pins and freshness": PR #973
        # lengthens the Conversion bullet, so the boundary must hold at any
        # bullet length.
        text = POST_973_ROADMAP_BULLET + ROADMAP_PINS_BULLET
        bullets = split_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertEqual(
            bullet_campaigns(bullets[0]), {"full-conversion-transient"}
        )
        self.assertEqual(bullet_campaigns(bullets[1]), set())

    def test_indented_subbullet_stays_with_parent(self) -> None:
        text = (
            "- **Signoff.** Two items are gated:\n"
            "  - Item 7 analog (`no_evidence`): no top-level `klt pex`.\n"
            "- **Conversion: overall FAIL.** newest record\n"
            "  (`sim/xyz/records/20261011-112119-188e94c.md`).\n"
        )
        bullets = split_bullets(text)
        self.assertEqual(len(bullets), 2)
        self.assertEqual(bullet_campaigns(bullets[0]), set())
        self.assertEqual(bullet_campaigns(bullets[1]), {"xyz"})

    def test_table_rows_and_paragraphs_are_not_bullets(self) -> None:
        # A `records/LATEST` mention inside a `## Next`-style table row is not
        # a top-level bullet and must not be gated by the bullet rules.
        text = (
            "| What | Done when | Issue |\n"
            "|---|---|---|\n"
            "| Repoint the manifest | cites the run that matches "
            "`records/LATEST` | #743 |\n"
            "\n"
            "A plain paragraph citing `sim/xyz/records/"
            "20261011-112119-188e94c.md` is likewise out of the gate's scope.\n"
        )
        self.assertEqual(split_bullets(text), [])

    def test_doc_without_bullets_yields_no_bullets(self) -> None:
        self.assertEqual(split_bullets("# Heading\n\nSome prose.\n"), [])


class TestTokenExtraction(FixtureCase):
    """Rules 1-2: only `sim/`-anchored path tokens name campaigns or stamps."""

    def test_campaign_and_stamp_from_sim_path_token(self) -> None:
        bullet = PRE_973_ROADMAP_BULLET
        self.assertEqual(bullet_campaigns(bullet), {"full-conversion-transient"})
        self.assertIn(CURRENT_RECORD_STAMP, set(RECORD_STAMP_RE.findall(bullet)))

    def test_bare_stamp_with_no_path_prefix_counts_as_stamp(self) -> None:
        # ROADMAP's post-#973 shape quotes the stamp bare; rule 4 must still
        # see it.
        bullet = (
            "- **Conversion.** newest (`sim/xyz/records/LATEST`, pointing at\n"
            f"  `{CURRENT_RECORD_STAMP}`).\n"
        )
        write_pointer(self.sim_root, "xyz", CURRENT_RECORD_STAMP)
        self.assertBulletPasses(bullet)

    def test_layout_stamp_is_never_a_sim_campaign(self) -> None:
        self.assertEqual(bullet_campaigns(ROADMAP_PINS_BULLET), set())

    def test_layout_stamp_alongside_sim_campaign_is_not_attributed(self) -> None:
        # A `layout/<block>/reports/<stamp>.md`-shaped token in the same
        # bullet as a `sim/` campaign neither names a campaign nor blocks the
        # rule-4 at-least-one match on the sim stamp.
        bullet = (
            "- **Conversion.** newest (`sim/xyz/records/LATEST`, pointing at\n"
            f"  `{CURRENT_RECORD_STAMP}`); the top-level layout run\n"
            "  (`layout/sar-adc-top/reports/20261001-211249-1ca34e6f.md`)\n"
            "  deliberately diverges (#743).\n"
        )
        write_pointer(self.sim_root, "xyz", CURRENT_RECORD_STAMP)
        self.assertEqual(bullet_campaigns(bullet), {"xyz"})
        self.assertBulletPasses(bullet)

    def test_pointer_tokens_prefixed_and_bare(self) -> None:
        prefixed = "- a. (`sim/xyz/records/LATEST`) current evidence.\n"
        bare = "- b. newest record of `xyz`, named in `records/LATEST`.\n"
        self.assertEqual(
            bullet_pointer_campaigns(prefixed, {"xyz", "other"}), {"xyz"}
        )
        self.assertEqual(
            bullet_pointer_campaigns(bare, {"xyz", "other"}), {"xyz", "other"}
        )
        self.assertEqual(bullet_pointer_campaigns(prefixed, {"abc"}), set())

    def test_reports_pointer_is_not_a_records_pointer(self) -> None:
        # `layout/sar-adc-top/reports/LATEST` must not satisfy rule 3 for a
        # sim campaign.
        bullet = (
            "- **Conversion.** newest\n"
            f"  (`sim/xyz/records/{CURRENT_RECORD_STAMP}`), while the\n"
            "  composed block's `layout/sar-adc-top/reports/LATEST` is a\n"
            "  later run.\n"
        )
        write_pointer(self.sim_root, "xyz", CURRENT_RECORD_STAMP)
        self.assertBulletFails(bullet, "never names its records/LATEST pointer")


class TestRulesOnFixtures(FixtureCase):
    """The gate must bite on synthetic defects, not merely agree with main."""

    def test_stamp_without_pointer_mention_fails(self) -> None:
        # The pre-#973 docs/ROADMAP.md shape, quoted verbatim: rule 3
        # (non-vacuity) is the rule that bites on the real defect.
        write_pointer(
            self.sim_root, "full-conversion-transient", CURRENT_RECORD_STAMP
        )
        self.assertBulletFails(
            PRE_973_ROADMAP_BULLET, "never names its records/LATEST pointer"
        )

    def test_moved_pointer_fails(self) -> None:
        # Negative control: the prose names the pointer and a stamp, but the
        # pointer has since moved on. Rule 4.
        write_pointer(
            self.sim_root, "full-conversion-transient", BOUNDARY_SWEEP_STAMP
        )
        self.assertBulletFails(
            README_CONVERSION_BULLET,
            f"no stamp in the bullet equals its target ({BOUNDARY_SWEEP_STAMP})",
        )

    def test_pointer_plus_non_pointer_record_passes(self) -> None:
        # PR #973's bullet names the pointer, quotes its target bare, and
        # additionally cites the #913 boundary sweep, which moves no pointer.
        # Additional stamps are legal (rule 4, per citation-gate check 3).
        write_pointer(
            self.sim_root, "full-conversion-transient", CURRENT_RECORD_STAMP
        )
        self.assertBulletPasses(POST_973_ROADMAP_BULLET)

    def test_readme_shape_passes(self) -> None:
        write_pointer(
            self.sim_root, "full-conversion-transient", CURRENT_RECORD_STAMP
        )
        self.assertBulletPasses(README_CONVERSION_BULLET)

    def test_pins_bullet_passes_layout_stamp_not_attributed(self) -> None:
        # Even with the campaign's pointer minted, the Pins bullet commits
        # nothing: its stamps are layout-run ids and its pointer is a
        # `reports/LATEST`.
        write_pointer(
            self.sim_root, "full-conversion-transient", CURRENT_RECORD_STAMP
        )
        self.assertBulletPasses(ROADMAP_PINS_BULLET)

    def test_campaign_without_pointer_is_skipped(self) -> None:
        # A campaign publishing no `records/LATEST` has nothing to be stale
        # against (rule 2) -- e.g. sim/comparator-decision, deliberately
        # pointerless.
        bullet = (
            "- **Comparator decision.** newest\n"
            "  (`sim/comparator-decision/records/"
            f"{CURRENT_RECORD_STAMP}`).\n"
        )
        self.assertBulletPasses(bullet)

    def test_doc_without_sim_citation_passes(self) -> None:
        text = "- **Layout.** DRC clean; see `layout/sar-adc-top/`.\n"
        self.assertEqual(check_text(text, self.sim_root), [])


class TestLiveTree(unittest.TestCase):
    """The live-tree assertion is separate from the fixture assertions."""

    def test_live_docs_match_pointers(self) -> None:
        violations = check_repo()
        self.assertEqual(
            violations,
            [],
            "guarded docs drift from the sim/*/records/LATEST pointers:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()

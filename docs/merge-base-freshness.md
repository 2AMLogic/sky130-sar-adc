# Merge-base freshness: why a PR's own green is not evidence about `main`

Decision record for issue #422. Status as of 2026-09-25: **decided, and
blocked on one operator action** (see "Operator hand-off" below).

## The failure this is about

`main` went red for about an hour on 2026-09-25 (issue #417). Two PRs were
each green on their own branch and semantically conflicted the moment both
landed:

- PR #415 merged at 09:38:13Z. It minted
  `sim/enob-estimate/records/20260925-090023-c3a6872.md` and re-pointed
  Section 4's ENOB row onto it.
- PR #414 merged at 09:40:17Z. It added the corner-grid census (citation-gate
  check 28), which enumerates the records Section 4 cites **by path**. Its
  branch predated #415, so the census it computed named the record #415 had
  just superseded.

Neither branch was ever evaluated against the tree it actually merged onto.
The citation gate caught the conflict two minutes later — on `main`, which is
where it runs, and which is the only place it could have caught it. PR #416
then merged red because it had rebased onto that `main`, and the repair needed
its own issue and PR (#421).

This is not a property of check 28. Every cross-cutting census this repository
gates — checks 6, 9, 12–21, 24–26, 28 — restates a fact derived from the whole
tree, and can be invalidated by a concurrent PR that never touches the
document. See `docs/citation-gate.md` for what each of them grades.

## The remedy already exists; it just has nothing to bind to

`.loom/scripts/merge-pr.sh` ships `_check_required_check_freshness()` (upstream
Loom issue #8248). It refuses to merge when a green **required** status check's
run started before the base branch's current tip commit time — the rule being
that a check result is evidence about one tree, and a moved base means that
tree no longer exists. It fails closed, and `--redate-stale-checks` can push a
tree-identical no-op commit to force fresh evidence instead.

It resolves *which* contexts are required from the forge. This repository
configures none, so the guard is inert. Verified live on 2026-09-25, on the
real #415 head, against the real `main`:

```
$ gh api repos/2AMLogic/sky130-sar-adc/branches/main --jq '{name,protected}'
{"name":"main","protected":false}

$ gh api repos/2AMLogic/sky130-sar-adc/rules/branches/main
[]

# PR #415's green "Repo checks (headless, no PDK)" started 2026-09-25T09:26:59Z.
# main's tip 0d5a4ff has commit time      2026-09-25T11:12:59Z.
# The green therefore predates the base tip by 1h46m -- precisely the condition
# the guard exists to refuse:
$ loom-daemon merge-pr stale-checks --pr 415 --repo 2AMLogic/sky130-sar-adc \
      --head-sha 38c80cfe2174dc0eee0d5c4866bb414bb31e61e3 --base-ref main
LOOM-STALE-CHECKS-CLEAN
(exit 0)
```

That is the whole bug: with zero required contexts the guard returns clean for
any PR, however stale. It did not fail to catch #414/#415 — it was never armed.

## The decision

**Arm the existing guard by declaring exactly one required status check on
`main`, as a repository ruleset.** Do not build anything new; do not require
branches to be up to date.

Three choices inside that, each made for a reason that is easy to get wrong:

**A ruleset, not classic branch protection.** The guard unions two sources
(#8103): the ruleset API (`GET /repos/{nwo}/rules/branches/{branch}`) and
classic protection (GraphQL `branchProtectionRule.requiredStatusCheckContexts`).
Only the first is readable by the fleet's GitHub App installation token —
verified 2026-09-25: the ruleset endpoint answers `200` with
`X-Accepted-GitHub-Permissions: metadata=read`, while
`GET /branches/main/protection` answers `403 administration=read`. The GraphQL
classic source does not *error* for a token without `administration`; it
resolves `branchProtectionRule` to `null`, which the guard reads as "nothing
is required". A requirement configured the classic way would therefore be
invisible to the guard it is supposed to arm, and invisible silently — the
forge would block a *failing* check while the *freshness* rule this issue is
about stayed off. Configuring it as a ruleset needs no new token scope.

**Only the headless job.** `Repo checks (headless, no PDK)` — the `checks` job
in `.github/workflows/ci.yml` — and nothing else. `pdk-smoke` is opt-in
(schedule / `workflow_dispatch` / `run-pdk-smoke` label) and usually reports
`skipped`, so requiring it would block every ordinary merge. Both it and
`signoff-check` sit behind the self-hosted runner whose queueing latency is
issue #354's subject. `checks` is the fast, always-on, PDK-free job, and it is
the one that runs the citation gate (`npm run check:ci` →
`check:proposal-citations`) that detected #417. Fork PRs are covered: `checks`
falls back to `ubuntu-latest` for them (`ci.yml`, `runs-on` expression) and
reports under the same check-run name either way.

**Not "require branches to be up to date".** That is a different mechanism, and
#8248's own design record already considered and rejected it for this fleet —
"it forces a rebase per merge at a cadence this fleet (125-commits-behind PRs
are ordinary) would pay constantly". So `strict_required_status_checks_policy`
is `false`. What the ruleset supplies is the *input* the freshness guard needs:
a context the forge calls REQUIRED, so the guard can judge that context's
evidence against the base tip and re-date it only when it is genuinely stale,
rather than rebasing unconditionally. Merge-queue (remedy 2 in #422) was not
needed: it would test the prospective merge result, which is strictly better
semantics, but it is more moving parts for the same outcome here and the guard
is already written and shipped.

Plan gating is not a constraint: this repository is public, and the ruleset
endpoint answers normally (the `PLAN-GATED REPOSITORIES` case documented in
`.loom/scripts/merge-pr.sh` applies to *private* repositories on GitHub Free).

The configuration is checked in as `.github/apply-required-status-checks.sh`
rather than described in prose, so that it is reviewable, re-appliable, and
re-derivable instead of a remembered sequence of checkboxes.

## Why not Loom's own installer — and the footgun that would have been

Loom ships the intended home for this setting: `.loom/config.json` →
`branchProtection.requiredStatusChecks`, applied by the Loom source repo's
`scripts/install/setup-branch-protection.sh`. That is where this belongs, and
it is not usable here yet.

The installer joins the configured context names into one comma-separated
string and re-splits it on `[,\n]+`, so a check-run name that *contains* a
comma is torn in half. `LOOM_DRY_RUN=true` on 2026-09-25, with
`"requiredStatusChecks": ["Repo checks (headless, no PDK)"]` configured,
previewed this:

```
"required_status_checks": [
  { "context": "Repo checks (headless" },
  { "context": "no PDK)" }
]
```

Neither context exists, and a required context that never reports blocks every
merge on `main` forever. That is strictly worse than today's silent no-op — it
would convert "the guard is not armed" into "nothing can merge", with the cause
two layers away from the symptom.

So `branchProtection` is deliberately **absent** from this repository's
`.loom/config.json`. Adding it now would arm that trap for whoever next runs
the installer or `loom update`, months from now, for unrelated reasons. The
bespoke script sends the contexts as a JSON array, which has no separator to
be ambiguous about. Two things would let this repo move back onto the shipped
path: the upstream split being fixed, or the `checks` job being renamed to
drop the comma. Renaming was rejected for now — the job name is the check-run
name the forge has been recording all along, and moving it to work around a
tool bug costs continuity in exactly the evidence trail this repository exists
to keep.

The bespoke ruleset is also named distinctly (`main: required status checks`,
versus the installer's `main`) so that the installer's cross-name overlap
detection sees it and defaults to "skip" rather than replacing it.

## Operator hand-off (the one thing an agent cannot do here)

The fleet's GitHub App installation has **no `administration` permission at
all** — not write, not read. Confirmed three ways on 2026-09-25, read probes
first:

| probe | result |
| --- | --- |
| `GET /repos/{nwo}/branches/main/protection` | `403` — `X-Accepted-GitHub-Permissions: administration=read` |
| `GET /orgs/2AMLogic/rulesets` | `403 Resource not accessible by integration` |
| `POST /repos/{nwo}/rulesets` (the real payload) | `403 Resource not accessible by integration`; `GET /rulesets` still returns `[]`, so nothing was created |

The `POST` probe was run last, after both read probes had already established
the answer, and it created nothing.

So the one-time change is an operator action. Either:

```
# As a repo admin (or any identity with administration=write):
./.github/apply-required-status-checks.sh --apply
```

or, equivalently, in **Settings → Rules → Rulesets → New branch ruleset**:
name `main: required status checks`, enforcement **Active**, target
**Default branch**, no bypass actors, one rule — **Require status checks to
pass**, with `Repo checks (headless, no PDK)` (source: GitHub Actions) added
and **Require branches to be up to date before merging** left **unchecked**.

Granting the App `administration: write` would let the fleet do this itself,
but that is a much larger standing permission than this one setting warrants,
and is not recommended on this repository.

## How to verify it landed, and that it actually works

Two commands, in order. Neither needs admin.

**1. The requirement is visible to the guard** — not merely configured
somewhere. `--check` reads the same endpoint the guard reads:

```
$ ./.github/apply-required-status-checks.sh --check
```

Before the hand-off this exits 1 with `NOT CONFIGURED` (its state as this
record is written). After, it exits 0.

**2. The guard now refuses stale evidence.** Replay the probe above against any
PR whose green `Repo checks` run predates `main`'s tip — the #415/`0d5a4ff`
pair is a permanent, already-measured instance of exactly that condition, so
the same one-line command is a repeatable before/after:

```
$ loom-daemon merge-pr stale-checks --pr 415 --repo 2AMLogic/sky130-sar-adc \
      --head-sha 38c80cfe2174dc0eee0d5c4866bb414bb31e61e3 --base-ref main
```

Today: `LOOM-STALE-CHECKS-CLEAN`, exit 0. After the ruleset exists this must
flip to exit 1 with a refusal naming the check and both timestamps. If it does
not flip, the requirement is not reaching the guard — most likely it was
configured as classic protection rather than as a ruleset, which is the exact
failure this record's first design choice exists to prevent, so re-read that
section before assuming the guard is broken.

Step 2 is a *pre-merge* assertion about the mechanism, not about a merge that
happened. **Still open**: nobody has yet observed the guard refuse a real
merge on this repository — i.e. re-run the #414/#415 race live (land one PR
that re-points a Section 4 citation, then attempt to merge a second, unrebased
PR carrying a census derived before it) and watch `merge-pr.sh` block or
re-date rather than land the conflict. Issue #422's acceptance criteria ask for
that observation, and it cannot be made until the hand-off above is done.

## What this does not fix

Only merges that go through `.loom/scripts/merge-pr.sh` consult the freshness
guard; the forge's own requirement (a *failing* or missing check blocks) binds
every path, including a hand-merge in the GitHub UI, but staleness does not. A
human who merges in the UI with a green-but-stale check still lands the #417
shape. The 40 most recent merged PRs (checked 2026-09-25) were merged by
`app/loom-fleet-dispatch` without exception, so the scripted path is the one
that matters today; if that stops being true, this gap becomes real rather
than theoretical.

It also does not make the census documents self-healing. A change that
re-points a Section 4 citation must still restate the census in the same
commit, as `docs/citation-gate.md`'s check 28 section says. What changes is
that a PR which merges onto a base where someone *else* did that is held until
its own gate has been re-run against that base.

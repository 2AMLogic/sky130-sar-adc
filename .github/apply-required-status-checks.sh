#!/usr/bin/env bash
# .github/apply-required-status-checks.sh -- declare (and verify) the ONE
# required status check on `main`, as a repository RULESET (issue #422).
#
# Why this exists at all
# ----------------------
# `.loom/scripts/merge-pr.sh`'s `_check_required_check_freshness()` (upstream
# Loom #8248) already refuses to merge a PR whose green REQUIRED check started
# before the base branch's current tip -- the exact failure that put `main` red
# on 2026-09-25 (#417: PR #415 and PR #414 were each green on their own stale
# base and semantically conflicted on merge). That guard resolves "REQUIRED"
# from the forge. This repository configures nothing as required, so the guard
# has nothing to bind to and returns clean on every merge. The fix is therefore
# configuration, not code -- see docs/merge-base-freshness.md for the full
# decision record, the live evidence, and the verification recipe.
#
# Why a RULESET and not classic branch protection
# -----------------------------------------------
# The guard unions two sources (#8103): the ruleset API
# (`GET /repos/{nwo}/rules/branches/{branch}`) and classic protection (GraphQL
# `branchProtectionRule.requiredStatusCheckContexts`). Only the first is
# readable by the fleet's GitHub App installation token -- verified live on
# 2026-09-25: the ruleset endpoint answers 200 with `X-Accepted-GitHub-
# Permissions: metadata=read`, while `GET /branches/main/protection` answers
# 403 `administration=read`. The GraphQL classic source does not error for a
# token without `administration`; it resolves `branchProtectionRule` to `null`,
# which the guard reads as "nothing required". A requirement configured the
# CLASSIC way would therefore be invisible to the very guard it is meant to
# arm, and invisible SILENTLY.
#
# Why not Loom's own scripts/install/setup-branch-protection.sh
# -------------------------------------------------------------
# That installer is the intended home for this setting
# (`.loom/config.json` -> `branchProtection.requiredStatusChecks`), and it
# should be once it can express this context name. It cannot today: it joins
# the configured contexts into one comma-separated string and re-splits on
# `[,\n]+`, so a check-run name CONTAINING a comma is torn in half. Verified
# with `LOOM_DRY_RUN=true` on 2026-09-25 -- the payload it would apply requires
# two contexts that do not exist:
#
#     "required_status_checks": [ { "context": "Repo checks (headless" },
#                                 { "context": "no PDK)" } ]
#
# A required context that never reports blocks every merge forever, so that
# payload would be strictly worse than today's no-op. `branchProtection` is
# therefore deliberately ABSENT from this repo's `.loom/config.json` until the
# upstream split is fixed -- adding it would arm that footgun for the next
# person who runs the installer or `loom update`. This script sends the
# contexts as a JSON array, which has no such ambiguity.
#
# Why only the headless job
# -------------------------
# `signoff-check` and `pdk-smoke` are deliberately NOT required. Both sit
# behind the self-hosted runner whose queueing latency is #354's subject, and
# `pdk-smoke` is opt-in (schedule / workflow_dispatch / `run-pdk-smoke` label),
# so requiring it would block every ordinary merge on a job that usually
# reports `skipped`. `checks` is the fast, always-on, PDK-free job, and it is
# the one that runs the citation gate (`npm run check:ci` ->
# `check:proposal-citations`) that detected #417 in the first place.
#
# `bypass_actors` is deliberately EMPTY, including for the fleet's own App: a
# merge path that can bypass the requirement is a merge path where the
# freshness guard's premise does not hold.
#
# `strict_required_status_checks_policy` is deliberately FALSE. "Require
# branches to be up to date before merging" is a different mechanism, and #8248
# already considered and rejected it for this fleet ("it forces a rebase per
# merge at a cadence this fleet -- 125-commits-behind PRs are ordinary -- would
# pay constantly"). What this ruleset supplies is the input that mechanism
# needs: a context the forge calls REQUIRED, so the freshness guard can judge
# that context's evidence against the base tip instead of rebasing
# unconditionally.
#
# The ruleset is named distinctly from Loom's own (`main`) on purpose: if the
# installer is ever run here, its cross-name overlap detection sees this one
# and defaults to "skip" rather than silently replacing it.
#
# Usage
# -----
#   ./.github/apply-required-status-checks.sh            # --check (default)
#   ./.github/apply-required-status-checks.sh --check    # read-only verdict
#   ./.github/apply-required-status-checks.sh --show     # print the payload
#   ./.github/apply-required-status-checks.sh --apply    # create the ruleset
#
# `--check` needs only `metadata=read` and is what anyone (or any agent) can
# run to establish whether the hand-off has landed. `--apply` needs
# `administration=write`, which the fleet's App installation does NOT have --
# it is an operator action. This script is NOT wired into `npm run check:ci`:
# that job is deliberately network-free, and a CI gate that fails until an
# operator clicks something is a red main, not a signal.

set -euo pipefail

NWO="${REPO_NWO:-2AMLogic/sky130-sar-adc}"
RULESET_NAME="main: required status checks"
# The `checks` job's `name:` in .github/workflows/ci.yml. This string is the
# check-run name the forge matches on; renaming the job there without renaming
# it here silently un-requires the check (which `--check` below reports).
CONTEXT="Repo checks (headless, no PDK)"
# The GitHub Actions app. Pinning it means a third-party app cannot satisfy
# this requirement by reporting a status of the same name.
ACTIONS_APP_ID=15368

payload() {
    jq -n --arg name "$RULESET_NAME" --arg ctx "$CONTEXT" --argjson app "$ACTIONS_APP_ID" '
      {
        name: $name,
        target: "branch",
        enforcement: "active",
        bypass_actors: [],
        conditions: { ref_name: { include: ["~DEFAULT_BRANCH"], exclude: [] } },
        rules: [
          {
            type: "required_status_checks",
            parameters: {
              strict_required_status_checks_policy: false,
              required_status_checks: [ { context: $ctx, integration_id: $app } ]
            }
          }
        ]
      }'
}

# Reads the same endpoint `loom-daemon merge-pr stale-checks` reads, so a PASS
# here means the guard sees the requirement -- not merely that something was
# configured somewhere.
check() {
    local required
    required="$(gh api "repos/$NWO/rules/branches/main" --jq \
        '.[]? | select(.type == "required_status_checks")
              | .parameters.required_status_checks[]?.context')"

    if [[ -z "$required" ]]; then
        echo "NOT CONFIGURED: repos/$NWO/rules/branches/main declares no required_status_checks rule."
        echo "  The #8248 required-check freshness guard is inert on this repository:"
        echo "  with zero required contexts it returns LOOM-STALE-CHECKS-CLEAN for any PR,"
        echo "  however stale that PR's evidence is. See docs/merge-base-freshness.md."
        echo "  Remedy (operator, needs administration=write): $0 --apply"
        return 1
    fi

    if ! grep -Fxq "$CONTEXT" <<<"$required"; then
        echo "DRIFT: a required_status_checks rule exists, but it does not require"
        echo "  '$CONTEXT'."
        echo "  Required today:"
        sed 's/^/    /' <<<"$required"
        echo "  Either the ci.yml job name moved without this script following it, or the"
        echo "  ruleset was edited by hand. See docs/merge-base-freshness.md."
        return 1
    fi

    echo "OK: '$CONTEXT' is a required status check on main,"
    echo "  and is visible at repos/$NWO/rules/branches/main -- the source the"
    echo "  #8248 freshness guard reads. Stale green evidence now blocks a merge."
    return 0
}

apply() {
    echo "Creating ruleset '$RULESET_NAME' on $NWO ..."
    payload | gh api -X POST "repos/$NWO/rulesets" --input - >/dev/null
    echo "Created. Verifying ..."
    check
}

case "${1:---check}" in
    --check) check ;;
    --show) payload ;;
    --apply) apply ;;
    -h | --help) sed -n '2,92p' "$0" ;;
    *)
        echo "unknown argument: $1 (expected --check, --show, --apply)" >&2
        exit 2
        ;;
esac

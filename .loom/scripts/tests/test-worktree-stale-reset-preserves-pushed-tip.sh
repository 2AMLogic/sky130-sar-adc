#!/usr/bin/env bash
# test-worktree-stale-reset-preserves-pushed-tip.sh — Tests for issue #475.
#
# LOCAL DIVERGENCE (this repo only). `.loom/scripts/worktree.sh` and this
# suite are pinned in `.loom/resync-ignore` because the fix they cover could
# not be upstreamed from this workspace: the forge credentials here are a
# GitHub App installation token scoped to the `2AMLogic` org, with no push/PR
# access to `rjwalters/loom`. Retire both pins (and this note) once the same
# fix lands in `defaults/scripts/worktree.sh` upstream. This suite is
# deliberately NOT added to `ci-wired.txt` / `ci-excluded.txt`: those manifests
# describe Loom's OWN CI partition, `check-ci-suite-manifest.sh` is not part of
# this repo's `npm run check:ci`, and editing them would widen the divergence
# for no local effect.
#
# THE INCIDENT (2026-09-26, `feature/issue-121`, open PR #470). worktree.sh's
# "worktree directory already exists and is registered with git" fast path
# decided preserve-vs-reset from two inputs only — commits ahead of BASE_REF,
# and `git status --porcelain`. A worktree parked at a plain `main` commit is
# legitimately 0-ahead and clean, so it scored "stale" and the LOCAL branch ref
# was `git reset --hard`-ed back to BASE_REF — moving it BACKWARDS past its own
# pushed tip, which was the head of an open PR:
#
#   ⚠ Worktree HEAD (21d25219…) is behind the pushed tip of branch
#     'feature/issue-121' (d3bd4469…) - this worktree may be stale
#   ⚠ Stale worktree detected (0 commits ahead, 9 behind main, no uncommitted changes)
#   ✓ Stale worktree reset to main
#
# The drift report on the first two lines had ALREADY computed the fact that
# makes the reset wrong, and then discarded it. The hazard is not the local
# ref: the dispatch environment exports `LOOM_FORCE_SCOPE=protected` so a
# headless agent can force-push its own branch, and a Builder/Doctor that
# committed from the reset state would have force-pushed `main + 1` over
# `origin/feature/issue-121`, ERASING the open PR's commits — recoverable only
# from a remote reflog nobody holds.
#
# Coverage (Tests 2-4 are the negative controls: the legitimately-stale reset
# path must still reset exactly as before):
#   1. HEAD is a STRICT ANCESTOR of `origin/<branch>` (the incident shape:
#      branch pushed ahead of main, worktree parked at an old main commit,
#      0 ahead of base, clean tree) -> the branch ref is PRESERVED, never
#      reset to the base ref, and never moved backwards past the pushed tip.
#   2. No `origin/<branch>` at all (branch never pushed) -> still resets.
#   3. `origin/<branch>` exists but HEAD is NOT an ancestor of it (the
#      squash-merged-and-main-moved-on shape) -> still resets.
#   4. HEAD is EQUAL to `origin/<branch>` and that tip is already contained in
#      the base ref (merged, ref not auto-deleted) -> no drift, still resets.
#
# Harness follows test-worktree-existing-dir-drift-check.sh: throwaway bare
# origin + repo under mktemp, copy worktree.sh + lib/, materialize the worktree
# with a REAL first `worktree.sh <N>` call so the fast path under test actually
# fires on the second invocation, then mutate to the shape under test.
#
# The mktemp root is resolved with `pwd -P` for the same reason that suite
# gives: on macOS /tmp symlinks to /private/tmp, and worktree.sh's orphan
# cleanup compares physical `git worktree list` paths against a resolved
# candidate, so a symlinked root makes the just-registered worktree look
# unregistered.
#
# No `loom_test_require_daemon_bin` here, deliberately: the guard under test is
# pure shell in worktree.sh and (unlike the #6257 drift REPORT, which is
# `loom-daemon worktree-upstream`) must hold with or without a daemon binary —
# its degradation would be a lost file, not a lost diagnosis. The harness
# pushes with `-u`, so `refs/remotes/origin/<branch>` is locally accurate
# without any fetch at all, and the assertions below are about the branch ref,
# not about any message the daemon prints.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKTREE_SH="$SCRIPTS_DIR/worktree.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

pass() { TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1)); echo -e "  ${GREEN}PASS${NC}: $1"; }
fail() { TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1)); echo -e "  ${RED}FAIL${NC}: $1"; }

# setup_repo <name> <issue> [--push-branch] [--advance-main]
#
# Builds a throwaway repo whose `main` starts at a single commit (captured as
# $BASE_COMMIT by the caller via `git rev-parse main` afterwards), branches
# `feature/issue-<issue>` off it with two commits, optionally pushes that
# branch, optionally advances `main` by two further commits, then materializes
# the worktree with a real `worktree.sh <issue>` call. Echoes
# "<repo-path> <worktree-relative-path>".
setup_repo() {
    local name="$1" issue="$2" push_branch="$3" advance_main="$4"
    local tmp
    tmp=$(cd "$(mktemp -d /tmp/loom-wtpushedtip.XXXXXX)" && pwd -P)
    git init -q -b main "$tmp/origin.git" --bare
    git init -q -b main "$tmp/$name"
    (
        cd "$tmp/$name"
        git config user.email t@t
        git config user.name t
        # A real Loom repo gitignores the runtime markers; this fixture must
        # too, or the `.loom-managed` sentinel worktree.sh writes into the
        # worktree root shows up in `git status --porcelain` and the
        # "no uncommitted changes" half of the staleness test never holds —
        # every case below would then preserve via the WRONG arm and the
        # suite would pass while proving nothing.
        printf '%s\n' '.loom/' '.loom-managed' '.loom-in-use' '.loom-checkpoint' > .gitignore
        git add .gitignore
        git commit -q -m "m1 (branch point)"
        git remote add origin "$tmp/origin.git"
        git push -q origin main

        mkdir -p .loom/scripts/lib .loom/hooks
        cp "$WORKTREE_SH" .loom/scripts/worktree.sh
        if [[ -d "$SCRIPTS_DIR/lib" ]]; then
            cp -R "$SCRIPTS_DIR"/lib/* .loom/scripts/lib/ 2>/dev/null || true
        fi
        chmod +x .loom/scripts/worktree.sh

        git checkout -q -b "feature/issue-$issue"
        echo f1 > f1.txt && git add f1.txt && git commit -q -m "f1 (PR commit 1)"
        echo f2 > f2.txt && git add f2.txt && git commit -q -m "f2 (PR head)"
        [[ "$push_branch" == "push" ]] && git push -q -u origin "feature/issue-$issue"

        git checkout -q main
        if [[ "$advance_main" == "advance" ]]; then
            echo m2 > m2.txt && git add m2.txt && git commit -q -m m2
            echo m3 > m3.txt && git add m3.txt && git commit -q -m m3
            git push -q origin main
        fi

        # First (real) invocation — registers the worktree exactly as an
        # earlier Builder pass would have left it.
        ./.loom/scripts/worktree.sh "$issue" >/dev/null 2>&1
    )
    echo "$tmp/$name .loom/worktrees/issue-$issue"
}

cleanup_repo() {
    local repo="$1"
    [[ -z "$repo" ]] && return 0
    rm -rf "$(dirname "$repo")"
}

run_worktree_sh() {
    local repo="$1" issue="$2" log="$3"
    (
        cd "$repo"
        ./.loom/scripts/worktree.sh "$issue" >"$log" 2>&1 || echo "EXIT_NONZERO" >>"$log"
    )
}

# --- Test 1: the incident — HEAD a strict ancestor of the pushed tip ---------
echo "Test 1: worktree HEAD parked at an old main commit, 0 ahead of base, clean, but origin/<branch> holds an open PR's commits -> branch ref preserved, NOT reset to base"
read -r REPO WT_REL <<< "$(setup_repo incident 401 push advance)"
WT="$REPO/$WT_REL"

BASE_COMMIT=$(git -C "$REPO" rev-list --max-parents=0 HEAD)   # m1, the branch point
PUSHED_TIP=$(git -C "$REPO" rev-parse "origin/feature/issue-401")
MAIN_TIP=$(git -C "$REPO" rev-parse "origin/main")

# Park the worktree (and with it the LOCAL branch ref) at m1 — an ancestor of
# BOTH origin/main and origin/feature/issue-401, clean tree. This is exactly
# the state a previous pass's stale-reset, or a checkout of the base, leaves.
git -C "$WT" reset --hard -q "$BASE_COMMIT"

PRE_AHEAD=$(git -C "$WT" rev-list --count "origin/main..HEAD")
if [[ "$PRE_AHEAD" -eq 0 ]]; then
    pass "fixture is the incident shape: 0 commits ahead of the base ref"
else
    fail "fixture is wrong: $PRE_AHEAD commits ahead of the base ref, expected 0"
fi
if [[ -z "$(git -C "$WT" status --porcelain)" ]]; then
    pass "fixture is the incident shape: clean working tree"
else
    fail "fixture is wrong: working tree is not clean"
fi
if git -C "$WT" merge-base --is-ancestor HEAD "$PUSHED_TIP" && \
   [[ "$(git -C "$WT" rev-parse HEAD)" != "$PUSHED_TIP" ]]; then
    pass "fixture is the incident shape: HEAD is a strict ancestor of origin/feature/issue-401"
else
    fail "fixture is wrong: HEAD is not a strict ancestor of the pushed tip"
fi

OUT_LOG="/tmp/wtpushedtip-incident.$$"
run_worktree_sh "$REPO" 401 "$OUT_LOG"

REF_AFTER=$(git -C "$REPO" rev-parse "feature/issue-401")

# THE assertion: the local branch ref must not have been moved backwards past
# the pushed tip. Preserved (still m1) or fast-forwarded (to the tip) both
# satisfy that; reset to the base ref does not.
if git -C "$REPO" merge-base --is-ancestor "$REF_AFTER" "$PUSHED_TIP"; then
    pass "local feature/issue-401 is still an ancestor-or-equal of its pushed tip (not moved backwards past it)"
else
    fail "local feature/issue-401 ($REF_AFTER) is no longer reachable from origin/feature/issue-401 ($PUSHED_TIP)"
    cat "$OUT_LOG"
fi

if [[ "$REF_AFTER" != "$MAIN_TIP" ]]; then
    pass "local feature/issue-401 was NOT reset to the base ref (origin/main)"
else
    fail "local feature/issue-401 was reset to origin/main — the #475 regression"
    cat "$OUT_LOG"
fi

if git -C "$REPO" rev-parse --verify --quiet "$PUSHED_TIP^{commit}" >/dev/null; then
    pass "the pushed tip's commits are still reachable locally (nothing orphaned)"
else
    fail "the pushed tip is no longer resolvable"
fi

if grep -qi "Stale worktree reset" "$OUT_LOG"; then
    fail "worktree.sh reported resetting the stale worktree"
    cat "$OUT_LOG"
else
    pass "worktree.sh did not report a stale-worktree reset"
fi

if grep -qi "preserving" "$OUT_LOG"; then
    pass "worktree.sh reported preserving the worktree"
else
    fail "worktree.sh printed no preserve message"
    cat "$OUT_LOG"
fi

if grep -q "EXIT_NONZERO" "$OUT_LOG"; then
    fail "worktree.sh exited nonzero on the preserve path"
    cat "$OUT_LOG"
else
    pass "worktree.sh exited 0"
fi
cleanup_repo "$REPO"
rm -f "$OUT_LOG"

# --- Test 2: negative control — branch never pushed -> still resets ----------
echo ""
echo "Test 2: no origin/<branch> at all (never pushed), 0 ahead of base, clean -> legitimately stale, still reset to base"
read -r REPO WT_REL <<< "$(setup_repo nopush 402 nopush advance)"
WT="$REPO/$WT_REL"

BASE_COMMIT=$(git -C "$REPO" rev-list --max-parents=0 HEAD)
MAIN_TIP=$(git -C "$REPO" rev-parse "origin/main")
git -C "$WT" reset --hard -q "$BASE_COMMIT"

OUT_LOG="/tmp/wtpushedtip-nopush.$$"
run_worktree_sh "$REPO" 402 "$OUT_LOG"

REF_AFTER=$(git -C "$REPO" rev-parse "feature/issue-402")
if [[ "$REF_AFTER" == "$MAIN_TIP" ]]; then
    pass "unpushed stale worktree still resets to the base ref (no false preserve)"
else
    fail "unpushed stale worktree was not reset (ref=$REF_AFTER, base=$MAIN_TIP)"
    cat "$OUT_LOG"
fi
if grep -qi "Stale worktree reset" "$OUT_LOG"; then
    pass "worktree.sh still reports the stale-worktree reset"
else
    fail "worktree.sh no longer reports the stale-worktree reset"
    cat "$OUT_LOG"
fi
cleanup_repo "$REPO"
rm -f "$OUT_LOG"

# --- Test 3: negative control — pushed tip diverged, HEAD not an ancestor ----
echo ""
echo "Test 3: origin/<branch> exists but HEAD is NOT an ancestor of it (squash-merged, main moved on) -> still reset to base"
read -r REPO WT_REL <<< "$(setup_repo squashed 403 push advance)"
WT="$REPO/$WT_REL"

MAIN_TIP=$(git -C "$REPO" rev-parse "origin/main")
# Park HEAD at main's tip: origin/feature/issue-403 branched before m2/m3, so
# main's tip is NOT an ancestor of the pushed tip (they have diverged) — the
# shape a squash merge leaves behind when the remote branch is not auto-deleted.
git -C "$WT" reset --hard -q "$MAIN_TIP"

OUT_LOG="/tmp/wtpushedtip-squashed.$$"
run_worktree_sh "$REPO" 403 "$OUT_LOG"

REF_AFTER=$(git -C "$REPO" rev-parse "feature/issue-403")
if [[ "$REF_AFTER" == "$MAIN_TIP" ]]; then
    pass "diverged-from-pushed-tip worktree still resets to the base ref"
else
    fail "diverged-from-pushed-tip worktree was not reset (ref=$REF_AFTER, base=$MAIN_TIP)"
    cat "$OUT_LOG"
fi
cleanup_repo "$REPO"
rm -f "$OUT_LOG"

# --- Test 4: edge case — HEAD EQUAL to the pushed tip, tip already in base ---
echo ""
echo "Test 4: HEAD equals origin/<branch> and that tip is already contained in the base ref (merged, ref not deleted) -> no drift, still reset to base"
read -r REPO WT_REL <<< "$(setup_repo merged 404 push nadvance)"
WT="$REPO/$WT_REL"

# Fast-forward main onto the branch tip and push: origin/feature/issue-404 is
# now an ancestor of origin/main, and the worktree's HEAD is exactly that tip.
(
    cd "$REPO"
    git merge -q --ff-only "feature/issue-404"
    git push -q origin main
)
MAIN_TIP=$(git -C "$REPO" rev-parse "origin/main")
PUSHED_TIP=$(git -C "$REPO" rev-parse "origin/feature/issue-404")

if [[ "$(git -C "$WT" rev-parse HEAD)" == "$PUSHED_TIP" ]]; then
    pass "fixture: worktree HEAD equals the pushed tip (no drift to detect)"
else
    fail "fixture is wrong: worktree HEAD does not equal the pushed tip"
fi

OUT_LOG="/tmp/wtpushedtip-merged.$$"
run_worktree_sh "$REPO" 404 "$OUT_LOG"

REF_AFTER=$(git -C "$REPO" rev-parse "feature/issue-404")
if [[ "$REF_AFTER" == "$MAIN_TIP" ]]; then
    pass "no-drift merged worktree behaves as before (reset to the base ref)"
else
    fail "no-drift merged worktree was not reset (ref=$REF_AFTER, base=$MAIN_TIP)"
    cat "$OUT_LOG"
fi
cleanup_repo "$REPO"
rm -f "$OUT_LOG"

# --- Summary ---
echo ""
echo "Tests run: $TESTS_RUN, Passed: $TESTS_PASSED, Failed: $TESTS_FAILED"
[[ $TESTS_FAILED -eq 0 ]] || exit 1

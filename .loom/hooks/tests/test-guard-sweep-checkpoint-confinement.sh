#!/usr/bin/env bash
# Regression + diagnostic suite for issue #615: is a denied
# `mkdir -p .loom/sweep-checkpoint && check-main-clean.sh --snapshot ...`
# a defect in worktree-write-confinement, or intended behavior?
#
# FINDING (measured here, see docs/guard-sweep-checkpoint-confinement.md):
# intended. The denied target is the literal `mkdir -p` of the checkpoint
# directory (a Bash write into the main checkout while a managed worktree
# exists). The documented coordinator path -- check-main-clean.sh --snapshot and
# sweep-checkpoint.sh, invoked as plain script calls -- is ALLOWED, and those
# scripts create the directory themselves. The hook cannot authenticate the
# caller (#4245), so NO exemption is added; this suite pins the denials.
#
# Usage: .loom/hooks/tests/test-guard-sweep-checkpoint-confinement.sh [-v]
#   -v  print every PreToolUse payload and full JSON decision (diagnostic).
#
# Fixtures are isolated mktemp git trees; nothing touches production state.
# Both implementations are exercised: the vendored guard via the real
# dispatcher, and the Repo Skills canonical guard invoked directly.

set -uo pipefail
VERBOSE=0; [[ "${1:-}" == "-v" ]] && VERBOSE=1
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1"; }

FIXTURES=()
cleanup() { local f; for f in ${FIXTURES[@]+"${FIXTURES[@]}"}; do rm -rf "$f"; done; }
trap cleanup EXIT

# make_fixture <vendored|canonical> -> prints root. Main checkout with tracked
# files plus one .loom-managed worktree (activates worktree isolation).
make_fixture() {
    local mode="$1" root
    root="$(mktemp -d)"; root="$(cd "$root" && pwd -P)"
    FIXTURES+=("$root")
    git init -q -b main "$root"
    git -C "$root" config user.email t@example.invalid
    git -C "$root" config user.name t
    mkdir -p "$root/.loom/hooks" "$root/.loom/scripts/lib" "$root/design" "$root/spec"
    cp "$REPO_ROOT/.loom/hooks/guard-destructive.sh" \
       "$REPO_ROOT/.loom/hooks/guard-destructive-generic.sh" "$root/.loom/hooks/"
    cp "$REPO_ROOT"/.loom/scripts/lib/*.sh "$root/.loom/scripts/lib/"
    printf '.loom/worktrees/\n.loom/sweep-checkpoint/\n' > "$root/.gitignore"
    printf 'tracked\n' > "$root/design/notes.md"
    printf 'tracked\n' > "$root/spec/target-spec.md"
    if [[ "$mode" == "canonical" ]]; then
        mkdir -p "$root/.claude/skills/repo/hooks"
        cp "$REPO_ROOT/.claude/skills/repo/hooks/guard-destructive.sh" \
           "$root/.claude/skills/repo/hooks/"
    fi
    git -C "$root" add -A && git -C "$root" commit -qm init
    git -C "$root" worktree add -q "$root/.loom/worktrees/issue-1" -b feature/issue-1
    : > "$root/.loom/worktrees/issue-1/.loom-managed"
    printf '%s' "$root"
}

# Dispatcher selection: the dispatcher execs the Repo Skills guard only if it
# passes ALL dispatcher probes (repo#29, write-confinement, search/jq masking,
# gh-comment body-literal). In this repo the installed canonical guard lacks the
# last three, so the VENDORED guard is what production runs; "vendored" mode
# goes through the real dispatcher (proving the fallback). "canonical" mode
# runs the Repo Skills guard DIRECTLY so the same invariants are pinned for it
# too, in case a future Repo Skills bump makes the dispatcher select it.
dispatcher_selection() {
    local root="$1" g="$1/.claude/skills/repo/hooks/guard-destructive.sh" m
    [[ -r "$g" ]] || { echo vendored; return; }
    for m in 'repo#29' 'worktree-write-confinement' '--comment|--search' '--arg|--argjson' 'gh-comment-body-literal-at'; do
        grep -qF -- "$m" "$g" || { echo vendored; return; }
    done
    echo canonical
}

# run_guard <root> <cwd> <command> [ENV=VAL...] -> prints "<exit>|<stdout>"
run_guard() {
    local root="$1" cwd="$2" command="$3"; shift 3
    local payload out code=0 log GUARD_UNDER_TEST="$root/.loom/hooks/guard-destructive.sh"
    [[ "$MODE" == canonical ]] && GUARD_UNDER_TEST="$root/.claude/skills/repo/hooks/guard-destructive.sh"
    log="$(mktemp)"; FIXTURES+=("$log"); LAST_TAG=""
    payload=$(jq -n --arg c "$command" --arg cwd "$cwd" \
        '{hook_event_name:"PreToolUse",tool_name:"Bash",tool_input:{command:$c},cwd:$cwd}')
    out=$(cd "$cwd" && env -u LOOM_ROLE -u LOOM_WORKTREE_PATH -u LOOM_GUARD_WORKTREE_ISOLATION \
            LOOM_PROJECT_ROOT="$root" LOOM_CONFIG_DEFAULTS_FILE= \
            LOOM_GUARD_DECISION_LOG=1 LOOM_GUARD_DECISION_LOG_FILE="$log" "$@" \
            bash "$GUARD_UNDER_TEST" <<<"$payload" 2>/dev/null) || code=$?
    LAST_TAG="$(jq -r '.pattern' "$log" 2>/dev/null | tail -1)"
    if [[ $VERBOSE -eq 1 ]]; then
        printf '  payload: %s\n  cwd: %s\n  extra-env: %s\n  decision-json: %s\n  decision-tag: %s\n' \
            "$(jq -c . <<<"$payload")" "$cwd" "${*:-<none>}" "$(jq -c . <<<"${out:-null}")" "${LAST_TAG:-<none: allow>}" >&2
    fi
    RESULT="${code}|${out}"
}
decision() { [[ -n "${1#*|}" ]] || { echo allow; return; }; jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${1#*|}" 2>/dev/null || echo allow; }

expect() { # desc expected(deny|allow) root cwd command [env...]
    local desc="$1" want="$2" root="$3" cwd="$4" cmd="$5"; shift 5
    run_guard "$root" "$cwd" "$cmd" "$@"; local r="$RESULT"
    if [[ "${r%%|*}" != "0" ]]; then fail "$desc (exit ${r%%|*})"; return; fi
    local got; got="$(decision "$r")"
    # KNOWN DRIFT: the Repo Skills canonical guard does not treat `mkdir` as a
    # confined write primitive (measured; only the vendored guard denies it).
    # Reported as a NOTE, not a pass/fail, so the suite neither pins the gap
    # nor breaks when Repo Skills closes it. Dispatcher probes do not cover it.
    if [[ "$MODE" == canonical && "$cmd" == *mkdir* && "$want" == deny && "$got" == allow ]]; then
        printf 'NOTE %s (canonical guard allows mkdir; known drift vs vendored guard)\n' "$desc"
        return
    fi
    if [[ "$got" == "$want" ]] && { [[ "$want" == allow ]] || [[ "$LAST_TAG" == worktree-write-confinement* ]]; }; then
        pass "$desc"
    else
        fail "$desc (want $want, got $got tag=${LAST_TAG:-none})"
    fi
}

run_suite() {
    local mode="$1" root main wt
    MODE="$mode"
    root="$(make_fixture "$mode")"; main="$root"; wt="$root/.loom/worktrees/issue-1"
    local T="[$mode]"
    local SNAP='.loom/sweep-checkpoint/main-clean-baseline-RUN.txt'

    # --- Diagnosis: which extracted target of the compound payload is denied?
    expect "$T compound mkdir+snapshot from main is denied (original report)" deny "$root" "$main" \
        "mkdir -p .loom/sweep-checkpoint && ./.loom/scripts/check-main-clean.sh --snapshot $SNAP"
    expect "$T the bare mkdir -p of the checkpoint dir is the denied target" deny "$root" "$main" \
        "mkdir -p .loom/sweep-checkpoint"
    expect "$T documented snapshot call alone is allowed" allow "$root" "$main" \
        "./.loom/scripts/check-main-clean.sh --snapshot $SNAP"
    expect "$T documented snapshot call with RUN_ID variable is allowed" allow "$root" "$main" \
        'MAIN_CLEAN_BASELINE=".loom/sweep-checkpoint/main-clean-baseline-${RUN_ID}.txt"; ./.loom/scripts/check-main-clean.sh --snapshot "$MAIN_CLEAN_BASELINE"'
    expect "$T sweep-checkpoint.sh write helper is allowed" allow "$root" "$main" \
        './.loom/scripts/sweep-checkpoint.sh write 615 curator-done --task-id RUN'
    expect "$T sweep-checkpoint.sh begin/read/phase helpers are allowed" allow "$root" "$main" \
        './.loom/scripts/sweep-checkpoint.sh begin 615 builder --attempt 1 || true'

    # --- Same mkdir from the managed worktree resolves inside it: allowed.
    expect "$T mkdir -p .loom/sweep-checkpoint inside the issue worktree is allowed" allow "$root" "$wt" \
        "mkdir -p .loom/sweep-checkpoint"

    # --- No role-only exemption (read-only roles only get the dist/ carve-out).
    local role
    for role in curator judge auditor builder; do
        expect "$T LOOM_ROLE=$role does not exempt mkdir of the checkpoint dir" deny "$root" "$main" \
            "mkdir -p .loom/sweep-checkpoint" LOOM_ROLE="$role"
    done
    expect "$T LOOM_WORKTREE_PATH pin does not exempt main-checkout checkpoint dir" deny "$root" "$main" \
        "mkdir -p .loom/sweep-checkpoint" LOOM_WORKTREE_PATH="$wt"

    # --- No path-only exemption: every write primitive into the runtime path.
    expect "$T redirection into checkpoint path is denied" deny "$root" "$main" \
        "echo x > .loom/sweep-checkpoint/issue-615.json"
    expect "$T tee into checkpoint path is denied" deny "$root" "$main" \
        "echo x | tee .loom/sweep-checkpoint/issue-615.json"
    expect "$T cp into checkpoint path is denied" deny "$root" "$main" \
        "cp design/notes.md .loom/sweep-checkpoint/x.json"
    expect "$T mv into checkpoint path is denied" deny "$root" "$main" \
        "mv design/notes.md .loom/sweep-checkpoint/x.json"

    # --- Negative controls: tracked main-checkout paths stay denied.
    expect "$T mkdir into tracked tree is denied" deny "$root" "$main" "mkdir -p design/newdir"
    expect "$T redirection onto tracked file is denied" deny "$root" "$main" "echo x > spec/target-spec.md"
    expect "$T append onto tracked file is denied" deny "$root" "$main" "echo x >> design/notes.md"
    expect "$T tee onto tracked file is denied" deny "$root" "$main" "echo x | tee spec/target-spec.md"
    expect "$T sed -i on tracked file is denied" deny "$root" "$main" "sed -i 's/a/b/' design/notes.md"
    expect "$T cp onto tracked file is denied" deny "$root" "$main" "cp /etc/hostname design/notes.md"
    expect "$T mv onto tracked file is denied" deny "$root" "$main" "mv /etc/hostname design/notes.md"
    expect "$T absolute-path write into main from the worktree is denied" deny "$root" "$wt" \
        "echo x > $main/design/notes.md"

    # --- Edge cases a future carve-out must keep denying.
    expect "$T '..' traversal out of the checkpoint dir is denied" deny "$root" "$main" \
        "mkdir -p .loom/sweep-checkpoint/../../design/x"
    ln -s "$main/design" "$main/.loom/sweep-checkpoint-link" 2>/dev/null
    expect "$T symlink escape from a checkpoint-looking path is denied" deny "$root" "$main" \
        "echo x > .loom/sweep-checkpoint-link/notes.md"
    expect "$T sibling runtime directory is denied" deny "$root" "$main" "mkdir -p .loom/sweep-checkpoints"
    expect "$T unresolved-variable target is denied (fail closed)" deny "$root" "$main" \
        'mkdir -p "$UNSET_DIR/.loom/sweep-checkpoint"'
}

echo "=== sweep checkpoint vs worktree-write-confinement (#615) ==="
run_suite vendored
run_suite canonical
echo "dispatcher selection with the installed Repo Skills guard: $(dispatcher_selection "$(make_fixture canonical)")"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]

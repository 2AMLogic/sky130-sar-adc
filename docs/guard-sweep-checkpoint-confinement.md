# Sweep checkpoint writes vs worktree-write-confinement (#615)

Private working note. Guard telemetry showed a denied sweep command
`mkdir -p .loom/sweep-checkpoint && ./.loom/scripts/check-main-clean.sh --snapshot <file>`.
No circuit or product failure is involved.

## Decision

The denial is **intended behavior**. No guard change, no exemption.

## Evidence

Reproduced with `.loom/hooks/tests/test-guard-sweep-checkpoint-confinement.sh -v`
(isolated `mktemp` git fixture, one `.loom-managed` worktree, payload fed to the
real `guard-destructive.sh` dispatcher from the main-checkout `cwd`, no
`LOOM_ROLE`/`LOOM_WORKTREE_PATH`).

| Command (cwd = main checkout)                          | Decision | Tag |
|--------------------------------------------------------|----------|-----|
| `mkdir -p .loom/sweep-checkpoint && ...--snapshot ...` | deny     | `worktree-write-confinement` |
| `mkdir -p .loom/sweep-checkpoint` alone                | deny     | `worktree-write-confinement` |
| `check-main-clean.sh --snapshot .loom/sweep-checkpoint/...` alone | allow | none |
| `sweep-checkpoint.sh write\|begin ...`                 | allow    | none |
| `mkdir -p .loom/sweep-checkpoint` from the issue worktree | allow (resolves inside it) | none |

- The rejected extracted target is the **literal `mkdir -p` directory**
  (`<main>/.loom/sweep-checkpoint`), not the snapshot output or the helper
  output: scripts perform their own writes, so the hook sees only the script
  path.
- `LOOM_ROLE` in {curator, judge, auditor, builder} and a `LOOM_WORKTREE_PATH`
  pin do not change the outcome. The only role carve-out is `dist/`.
- The hook cannot identify the caller (#4245), so a coordinator-only exemption
  has no trustworthy signal to key on; a path-only or role-only exemption was
  rejected by the issue. Other primitives (`>`, `tee`, `cp`, `mv`) reach the same
  path, so keying on `mkdir` spelling would be bypassable.

## Correct coordinator path

Do not issue a raw `mkdir -p .loom/sweep-checkpoint`. Both helpers create the
directory themselves (verified: `check-main-clean.sh --snapshot` runs `mkdir -p`
on the parent of the snapshot file; `sweep-checkpoint.sh write` creates
`.loom/sweep-checkpoint/` before its atomic write). The lifecycle doc
(`.claude/commands/loom/sweep-wave-lifecycle.md`, step 0) already prescribes only
the two script calls and contains no `mkdir`; the denied command was an
improvised addition. That file is Loom-managed, so no local edit was made.

## Dispatcher / implementation notes

- In this repo the installed Repo Skills guard
  (`.claude/skills/repo/hooks/guard-destructive.sh`) fails the dispatcher
  probes (no `--comment|--search`, `--arg|--argjson`, or
  `gh-comment-body-literal-at` markers), so the **vendored**
  `guard-destructive-generic.sh` handled the reproduction.
- Drift: run directly, the Repo Skills guard does **not** treat `mkdir` as a
  confined write (it allows it) while it does deny `>`, `tee`, `sed -i`, `cp`,
  `mv`. If a Repo Skills bump ever makes the dispatcher select it, `mkdir`
  confinement silently disappears. The suite reports this as a `NOTE`. Tool gap
  to raise generically at the Loom/Repo Skills trackers; not fixed here.

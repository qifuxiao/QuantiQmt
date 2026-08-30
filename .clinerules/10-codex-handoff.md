# Cline Codex Handoff Protocol

This file defines the cross-server handoff constraints between Codex (planning / review)
and Cline (implementation). It references `AGENTS.md` and `spec/` but does **not** copy
business contract content.

## Authority chain

Read in order before any modification:

1. `AGENTS.md`
2. `spec/manifest.yaml`
3. the single active task in `tasks/active/`
4. all task `spec_refs`
5. this file (`.clinerules/10-codex-handoff.md`)

## Pre-flight (before any modification)

1. Run `git fetch origin --prune`.
2. Confirm the worktree is **clean** (`git status --porcelain` must be empty).
   A **dirty** worktree is a `PLAN_BLOCKED` condition.
3. Confirm the exact **Implementation Base SHA** recorded in the task matches
   `git merge-base origin/main HEAD`.
4. Confirm the **Planning Base SHA** is an ancestor of the Implementation Base
   (`git merge-base --is-ancestor <Planning Base> <Implementation Base>` exit 0).
5. Confirm the branch was created from the exact Implementation Base.
6. If any check fails, return **PLAN_BLOCKED** with the failing command, exit code,
   and evidence. Do not proceed, improvise, or modify task / spec to work around the
   block.

## PLAN_BLOCKED conditions

Return `PLAN_BLOCKED` (stop and report; do **not** improvise) when any of the
following is true:

- The worktree is **dirty** (untracked, modified, or staged files outside the
  current task scope).
- The Implementation Base SHA does not match the recorded value, or the Planning
  Base is not an ancestor of the Implementation Base.
- The active task count is not exactly one, or dependency status is unexpected.
- A **design gap** is detected that would require modifying `spec/`, the task,
  or adding a new business contract.
- A required path is not in `allowed_paths`, or a forbidden path would be touched.
- Verification commands cannot be executed or pass.
- GitHub permissions are insufficient to push or create a PR.

`PLAN_BLOCKED` must include: the failing command, exit code, and evidence.
Cline must not substitute its own plan or modify task / spec to work around the
block.

## Implementation Report (required after implementation)

After implementing and verifying, Cline must produce an **Implementation Report**
containing all of the following:

- Task ID
- Packet version / Plan version
- Planning Base SHA
- Implementation Base SHA
- Head SHA (`git rev-parse HEAD` at the time of the report)
- Branch name
- PR URL
- Changed files (full list)
- Per-acceptance-criterion evidence
- Every verification command with its **exit code**
- First-failing test evidence (test-first proof)
- Final test results
- **Allowed / forbidden-path audit** result (full diff path membership)
- **Unverified** scope
- **Risk**s
- Spec **deviation**s
- Explicit statement: not merged, not self-approved, not closed out

## Prohibitions

- **No direct push to main.** All changes go through a branch and a PR.
- **No force-push.**
- **No self-approve.** Cline cannot approve its own PR.
- **No merge.** Only a human may merge.
- **No closeout.** Moving a task to `completed` is a human or independent Review
  decision, not an implementer decision.
- **No modification of task, spec, or activation status.**
- **No modification of `.github/` or branch protection.**

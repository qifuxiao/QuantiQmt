# QuantiQmt Cline Entry

Before any work:

1. Read `/AGENTS.md` completely.
2. Read `/spec/README.md` and `/spec/manifest.yaml`.
3. Read `/tasks/active/README.md` and the single `/tasks/active/TASK-*.md`.
4. Read every specification named by the task `spec_refs` and any closer `AGENTS.md`.
5. Check dependencies, git status, `allowed_paths`, `forbidden_paths`, acceptance criteria and
   `verification.commands`.

Do not implement when there is no active task. Do not activate, widen, complete or waive a task.
Do not copy business contracts into this file; `spec/` is authoritative.

For Mini QMT work, M1 requires an allowlisted simulation account, defaults to read-only with the Kill
Switch engaged, and forbids real-money trading. Strategy cannot call xtquant. Preserve
`OrderIntent → OMS registration → Risk → OMS transition → Execution`; UNKNOWN outcomes require
same-identity reconciliation without blind retry.

Use `/ai/workflows/implement-task.md` for implementation evidence and `/ai/workflows/review-task.md`
for independent Review. Run every task `verification.commands` command before handoff.

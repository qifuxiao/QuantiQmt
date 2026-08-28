# Prompt Template: Mini QMT M1 Task

Copy this template into Codex or Cline only after a human has activated the referenced task.

```text
Task: TASK-XXX

Implement only the single active task in tasks/active/ for the Mini QMT M1 delivery.

Before editing:
- Read AGENTS.md, spec/README.md, spec/manifest.yaml and every active task spec_refs.
- Check task dependencies, git status, allowed_paths and forbidden_paths.
- Report the concrete operator-visible outcome this task will add.

Required safety:
- Use only the designated Mini QMT simulation account; real-money trading is forbidden.
- Default to read-only, order sending disabled and Kill Switch engaged.
- Never place credentials, passwords, raw account identifiers or tokens in code, Git, tests or logs.
- Preserve OrderIntent → OMS registration → Risk → OMS transition → Execution.
- Treat uncertain external outcomes as UNKNOWN and reconcile the same identity; never blind retry.
- Keep backtest/live Domain and Application semantics shared; adapters may differ.

Implementation:
- Write or update a failing test first.
- Modify only allowed_paths and do the minimum implementation for the acceptance criteria.
- Add bounded timeouts, failure paths, structured logs/metrics and audit evidence required by spec.
- Do not change contracts or dependencies; report a spec gap instead.

Verification and handoff:
- Run every verification.commands entry and report exit codes.
- Map every acceptance criterion to evidence.
- Report changed files, unverified scope, risks and spec deviations.
- Do not self-approve, merge, release, move the task to completed or activate another task.
```

Codex and Cline must not treat this template as authorization. `tasks/active/`, its `allowed_paths` and
its `verification.commands` remain controlling；没有人类授权时不得自行激活任何 task。

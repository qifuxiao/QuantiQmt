# Prompt Template: Mini QMT M1 Task

Copy this template into an assigned tool only after a Human has activated the referenced task.

Shared roles are tool-neutral: Coordinator prepares the Packet; one Implementation Agent writes the
PR; an Environment Verification Agent supplies capability-bound evidence; an Independent Review Agent
reviews the exact Head; Human alone authorizes activation, external side effects, merge and closeout.
Codex and Cline are adapters and may fill a role only through verifiable GitHub assignment.

```text
Task: TASK-XXX
Role: Implementation Agent

Implementation assignment:
- Tool / OS:
- Exact Starting Head:
- Human evidence URL:
- Single-writer stop point:
- Ordered PR/branch single-writer records (PR + branch, agent, active true/false, previous stop_head):

Verification lanes:
- portable: required | optional | not_applicable
- windows: required | optional | not_applicable
- windows_miniqmt: required | optional | not_applicable

Environment evidence:
- Task / expected Base / exact Head / lane / requirement:
- Producer role / tool / OS / Python / Poetry / sanitized xtquant version as applicable:
- Original command / exit code / executed / passed / failed / skipped / RFC3339 timestamp:
- sanitized_evidence: true / explicit unverified_scope (empty allowed) / durable GitHub evidence URL:
- explicit real_money: false / simulation_order boolean:

Required-lane satisfaction:
- Validate every record's schema and task/Base/Head identity.
- Compare the complete record set with the task's exact expected command set; reject missing,
  unexpected or substitute commands.
- Require exit code 0, failed 0, non-negative internally consistent counts and executed greater than 0.
- Permit skips only within an explicit per-command allowance and record every allowed skip in a
  non-empty unverified_scope.

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
- Run every supported portable command; Linux evidence cannot satisfy Windows or Windows/Mini QMT lanes.
- Bind all evidence to the exact Head. A Head change invalidates environment evidence and Review.
- Treat well-formed evidence and required-lane satisfaction as separate gates. Only an Implementation
  Agent or Environment Verification Agent may produce environment evidence.
- Enforce PR/branch single-writer across all records; a Human-authorized switch requires previous/next
  identity, an earlier inactive previous record, and equal previous record stop_head, switch
  previous_agent_stop_head and next Starting Head.
- Never accept record-only simulation-order authorization; require trusted caller context binding the
  active task and durable Human GitHub evidence. Real-money evidence is always invalid.
- Missing required Windows/Mini QMT capability is BLOCKED, not a reason to downgrade acceptance.
- Map every acceptance criterion to evidence.
- Report changed files, environment evidence, unverified scope, risks and spec deviations.
- Do not self-approve, merge, release, move the task to completed or activate another task.
```

Codex and Cline must not treat this template as authorization. `tasks/active/`, its `allowed_paths` and
its `verification.commands` remain controlling；没有人类授权时不得自行激活任何 task。

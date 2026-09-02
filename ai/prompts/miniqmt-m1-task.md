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
- Agent ID / GitHub login / repository / PR:
- Tool / OS:
- Exact Starting Head:
- Human evidence URL:
- Single-writer stop point:
- Ordered ASSIGN / STOP / SWITCH events (strict sequence, PR + branch + then-current PR Head):
- Tool is a bounded safe identifier; OS is Windows, Linux or macOS. An adjacent agent change is always
  a switch requiring complete previous/next/stop-Head fields and no repeated agent identity key.
- Use an unedited canonical `QUANTIQMT_GITHUB_AUTHORITY_V1` PR issue comment. The Handoff freezes its
  ID/URL/author/timestamps/raw-body SHA-256 and producer allowlist; the formal gate reads it and the
  live PR through the fixed GitHub API. Caller PR/branch/Head fields or local assignment files are not authority.
  The GitHub API validates the canonical environment evidence comment with no redirects.

Verification lanes:
- portable: required | optional | not_applicable
- windows: required | optional | not_applicable
- windows_miniqmt: required | optional | not_applicable

Environment evidence:
- Publish one unedited canonical `QUANTIQMT_ENVIRONMENT_EVIDENCE_V1` PR issue comment.
- Envelope task / Plan / repository / PR / expected Base / live exact Head / assignment comment:
- Producer agent ID / GitHub login / role / tool / OS / authorized lanes:
- Record lane / requirement / Python / Poetry / trusted xtquant provenance as applicable:
- Original command / exit code / executed / passed / failed / skipped / RFC3339 timestamp:
- sanitized_evidence: true / explicit unverified_scope (empty allowed); GitHub API object supplies comment ID/URL:
- explicit real_money: false / miniqmt_connection / account_query / simulation_order booleans:
- xtquant provenance uses trusted source + opaque sanitized value + verified; no semver guess, path,
  whitespace/control, userdata/account/secret label or long digit-only value:

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
- Use bounded, no-redirect HTTPS GET to the fixed GitHub API to verify live PR OPEN/Base/Head/branches,
  canonical Human authority and evidence comment author/content. Any API failure is `BLOCKED`.
- Validate ordered assignment and evidence with `ai/schemas/agent-assignment.schema.yaml`,
  `ai/schemas/agent-environment-evidence.schema.yaml`, and the only formal machine gate
  `scripts/validate_agent_environment.py`.
- Read required/prohibited lanes and opaque exact commands only from the exact active task and frozen
  Handoff. Require an exact command partition; caller/evidence cannot override it. Do not build a
  universal PowerShell/POSIX parser or a shell-keyword blacklist.
- Treat well-formed evidence and required-lane satisfaction as separate gates. Only an Implementation
  Agent or Environment Verification Agent may produce environment evidence.
- Enforce PR/branch single-writer through strictly ordered `ASSIGN`, `STOP`, `SWITCH` events. A
  Human-authorized switch requires previous/next identity and equal STOP Head,
  `previous_agent_stop_head_sha`, next `starting_head_sha` and then-current `pr_head_sha`.
- Never accept record-only simulation-order authorization; require trusted caller context binding the
  active task and durable Human GitHub evidence. Real-money evidence is always invalid.
- Missing required Windows/Mini QMT capability is BLOCKED, not a reason to downgrade acceptance.
- Map every acceptance criterion to evidence.
- Report changed files, environment evidence, unverified scope, risks and spec deviations.
- Do not self-approve, merge, release, move the task to completed or activate another task.
```

Codex and Cline must not treat this template as authorization. `tasks/active/`, its `allowed_paths` and
its `verification.commands` remain controlling；没有人类授权时不得自行激活任何 task。

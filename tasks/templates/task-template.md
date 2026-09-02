---
id: TASK-XXX
title: Replace with a single outcome
status: blocked
depends_on: []
spec_refs: []
allowed_paths: []
forbidden_paths: []
verification:
  commands: []
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands: []
  prohibited_lanes: []
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

One observable outcome.

## Codex Implementation Plan

- Plan version: `TASK-XXX-PLAN-vX`
- Planning Base SHA: `<full SHA of main when Codex formed the plan>`
- Implementation Base SHA: `<provided by Codex in the Handoff Record as expected_base_sha; the Implementation Agent must not derive this from origin/main>`

### Implementation assignment

- Role: `Implementation Agent`
- Agent ID / GitHub login: `<authorized producer identity>`
- Repository / PR / Base branch / Head branch: `<frozen GitHub identity>`
- Tool / OS: `<assigned tool and actual operating system>`
- Exact Starting Head: `<40-char SHA>`
- Human evidence URL: `<durable GitHub comment/review URL>`
- Single writer: `<true; previous agent / next agent / stop Head when switching>`
- PR/branch single-writer: `<ordered ASSIGN / STOP / SWITCH events with strictly increasing sequence>`

Tool 使用最长 64 字符、无空白/控制字符的工具中立安全标识符；OS 必须是 Windows、Linux 或
macOS。agent identity 是独立且不复用的 writer/session 标识，不等于 tool/OS；同一 tool/OS
的不同会话可使用不同 identity。assignment 必须符合 `ai/schemas/agent-assignment.schema.yaml`：
正式事件只有 `ASSIGN`、`STOP`、`SWITCH`。前任 STOP Head、SWITCH starting Head 与当时 PR Head 必须完全相等，且
Human GitHub evidence 可核验；事件乱序或双 writer 均 fail-closed。

Human assignment 必须是目标 PR 上未编辑的 canonical
`QUANTIQMT_GITHUB_AUTHORITY_V1` issue comment。Repair Handoff 冻结 comment identity、raw-body
SHA-256 和 producer allowlist；正式 gate 通过固定 GitHub API 有界 HTTPS GET 实时读取 PR 与
comment。不得用 caller `--pr-head`/`--pr`/`--branch`、聊天或本地 assignment 文件替代。
The GitHub API validates the canonical environment evidence comment with no redirects.

The Environment Verification Agent produces evidence only; the Independent Review Agent reviews the
exact Head only; Human alone authorizes activation, external side effects, merge and closeout. A switch
must follow the previous STOP event and prove previous/next agent, `stop_head_sha` ==
`previous_agent_stop_head_sha` == next `starting_head_sha` == the then-current `pr_head_sha`.

### Verification lanes

| lane | required / optional / not_applicable | capability owner |
|---|---|---|
| `portable` | `<value>` | Linux or Windows with project dependencies |
| `windows` | `<value>` | actual Windows Agent |
| `windows_miniqmt` | `<value>` | actual Windows + task-approved Mini QMT environment |

### Environment evidence

Formal contracts and gate:

- `ai/schemas/agent-assignment.schema.yaml`
- `ai/schemas/agent-environment-evidence.schema.yaml`
- `scripts/validate_agent_environment.py` (the only formal machine gate)

Canonical GitHub environment evidence gate:

- 未编辑 `QUANTIQMT_ENVIRONMENT_EVIDENCE_V1` PR issue comment ID/URL/author/timestamps:
- Envelope task / Plan / repository / PR / expected Base / live exact Head / assignment comment:
- Producer agent ID / GitHub login / role / tool / OS / authorized lanes:
- Record lane / requirement (`required`, `optional`, `not_applicable`) / Python / Poetry / trusted xtquant provenance:
- Original command / exit code / executed / passed / failed / skipped / RFC3339 timestamp:
- `sanitized_evidence: true` / explicit `unverified_scope` (empty allowed):
- Explicit `real_money: false` / `miniqmt_connection` / `account_query` / `simulation_order` booleans:

Applicable xtquant version is `{source, value, verified}` provenance. Source must be trusted package
metadata or vendor API; value is a bounded opaque token and is not guessed as semver. Paths,
whitespace/control characters, `userdata_mini`, account or secret-like labels, and long digit-only
values are invalid and remain unverified/`BLOCKED`.

Required-lane satisfaction gate over the complete record set:

- Task/Handoff deep-equal required lanes and prohibited lanes:
- Frozen opaque exact command set / observed command set / missing or unexpected commands:
- Every record schema and task/Base/Head identity valid:
- Every exit code 0, failed 0, counts non-negative and internally consistent, executed greater than 0:
- Per-command skip allowance / skipped scope recorded in non-empty `unverified_scope`:

Only an Implementation Agent or Environment Verification Agent may produce environment evidence.
Well-formed evidence alone does not satisfy a required lane. Head changes invalidate all environment
evidence and Independent Review verdicts. A missing or unsatisfied required lane is `BLOCKED`; another
OS, mock, substitute command or narrative cannot replace it.

An evidence record cannot authorize its own simulation order. The satisfaction caller must supply a
trusted authorization context binding the active task and durable Human GitHub evidence; real money is
always forbidden.

The formal gate reads the live PR, canonical assignment and evidence comments through the fixed GitHub
API, then reads expected commands only from the exact active task and frozen Handoff. Lane
commands form an exact partition of `verification.commands`; caller/evidence cannot override them.
Commands are opaque exact strings. This template does not define a universal PowerShell/POSIX parser.

### Design

Observable outcome and key architectural decisions.

### File-level change plan

- `path/to/file`: what changes and why.

### Acceptance-to-test mapping

- Acceptance criterion → test function.

### Failure and recovery design

- Conditions that trigger `PLAN_BLOCKED`.
- Recovery or repair path for each failure mode.

### PLAN_BLOCKED conditions

- Conditions under which the Implementation Agent must stop and return `PLAN_BLOCKED`.

## Non-goals

- Explicitly excluded work.

## Deliverables

- Files, behavior and tests to produce.

## Acceptance criteria

- [ ] Objective, testable condition.

## Required evidence

- Commands, output summary and changed files.
- Implementation assignment, verification lanes, environment evidence, exact Head and unverified scope.
- Completion evidence must identify mode, change PR, reviewed head SHA, review verdict/reviewer/evidence URL, merge commit SHA and human authorization. Unknown historical facts are `unverifiable` with `reported_unverified`, prohibited release and a remediation task or valid waiver.

## Risks and rollback

- Known risks and safe rollback.

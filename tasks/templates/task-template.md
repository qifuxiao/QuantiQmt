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
- Tool / OS: `<assigned tool and actual operating system>`
- Exact Starting Head: `<40-char SHA>`
- Human evidence URL: `<durable GitHub comment/review URL>`
- Single writer: `<true; previous agent / next agent / stop Head when switching>`
- PR/branch single-writer: `<ordered PR + branch records; active true/false and stop_head for every previous writer>`

The Environment Verification Agent produces evidence only; the Independent Review Agent reviews the
exact Head only; Human alone authorizes activation, external side effects, merge and closeout. A switch
must occur after the previous record and prove previous/next agent, previous record `stop_head` == switch
`previous_agent_stop_head` == next Starting Head, and previous writer inactive.

### Verification lanes

| lane | required / optional / not_applicable | capability owner |
|---|---|---|
| `portable` | `<value>` | Linux or Windows with project dependencies |
| `windows` | `<value>` | actual Windows Agent |
| `windows_miniqmt` | `<value>` | actual Windows + task-approved Mini QMT environment |

### Environment evidence

Single-record schema/identity gate:

- Task / expected Base / exact Head / lane / requirement (`required`, `optional`, `not_applicable`):
- Producer role / tool / OS / Python / Poetry / sanitized xtquant versions as applicable:
- Original command / exit code / executed / passed / failed / skipped / RFC3339 timestamp:
- `sanitized_evidence: true` / explicit `unverified_scope` (empty allowed) / durable GitHub evidence URL:
- Explicit `real_money: false` / `simulation_order` boolean:

Required-lane satisfaction gate over the complete record set:

- Exact expected command set / observed command set / missing or unexpected commands:
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

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
- Implementation Base SHA: `<resolved after Activation PR merge; Cline records
  git rev-parse origin/main before creating the branch>`

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

- Conditions under which Cline must stop and return `PLAN_BLOCKED`.

## Non-goals

- Explicitly excluded work.

## Deliverables

- Files, behavior and tests to produce.

## Acceptance criteria

- [ ] Objective, testable condition.

## Required evidence

- Commands, output summary and changed files.
- Completion evidence must identify mode, change PR, reviewed head SHA, review verdict/reviewer/evidence URL, merge commit SHA and human authorization. Unknown historical facts are `unverifiable` with `reported_unverified`, prohibited release and a remediation task or valid waiver.

## Risks and rollback

- Known risks and safe rollback.

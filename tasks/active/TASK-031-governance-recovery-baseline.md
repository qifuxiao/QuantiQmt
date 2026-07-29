---
id: TASK-031
title: Restore governance state and establish machine-verifiable recovery baseline
status: active
depends_on: [TASK-014]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/README.md
  - tasks/templates/task-template.md
  - tasks/index.yaml
  - tasks/active/README.md
  - tasks/active/TASK-031-governance-recovery-baseline.md
  - tasks/backlog/TASK-005-risk-engine.md
  - tasks/backlog/TASK-016-strategy-runtime-contracts.md
  - tasks/completed/TASK-016-strategy-runtime-contracts.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/completed/TASK-004-persistence-outbox.md
  - tasks/completed/TASK-030-risk-validator-integration-scope.md
  - scripts/validate_specs.py
  - tests/spec/test_validate_specs.py
  - ai/README.md
  - ai/workflows/implement-task.md
  - ai/workflows/review-task.md
  - ai/workflows/team-collaboration.md
  - ai/governance/**
forbidden_paths:
  - spec/**
  - docs/**
  - src/**
  - migrations/**
  - .github/**
  - pyproject.toml
  - poetry.lock
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

恢复任务、规范、实现、Review 与发布状态的一致性，并建立可机器验证的治理基线。本任务不改变业务代码、公开事件、DTO、Schema、Workflow 或其他规范契约。

## Non-goals

- 不实现 Risk、Strategy、Persistence 或任何业务运行时代码。
- 不修改 `spec/**`、`src/**`、`tests/**`（除获批的 validator test）、migrations 或 PR #40。
- 不虚构历史 Review、Approve、CI、merge 或 release 证据。

## Acceptance criteria

- [ ] 队列目录、front matter、`tasks/index.yaml` 与 active README 一致，且唯一 active task 为 TASK-031。
- [ ] 机器可区分 contract、task、implementation-review、release 四类状态；不得复用一个 status 字段表达全部生命周期。
- [ ] 为 TASK-004/005/016/029/030 建立可审计 Evidence；无法证明的历史事实必须标记 `unverifiable`，不得补造 APPROVE。
- [ ] 扩展 `validate_specs` 检查目录/status/index、active README、依赖激活门禁、completed criteria/evidence，或明确报告 legacy gap。
- [ ] 建立 OrderIntent→OMS→Risk→Outbox→Execution、Inbox/Event Backbone、Strategy/Market 责任矩阵。
- [ ] 建立 ADR-0008、Risk 去重、manifest/docs lifecycle、Strategy event activation 偏差清单，并派生后续任务建议；本任务不修改业务或规范契约。
- [ ] 所有验证通过，且无业务代码或契约变化。

## Governance authorization and evidence

- Human members explicitly authorized this governance freeze, unified task-state recovery, TASK-016 completion migration, TASK-029 blocking, and creation of this recovery task.
- PR #46 was closed before this task; its branch and commits are not reused and are not evidence.
- TASK-016 completion evidence is retained in its completed task file; TASK-029 is frozen until TASK-031 completion and independent Review.

## Required evidence

- Record exact base/head/merge/review/release facts; mark every unproven historical claim `unverifiable`.
- Record validation commands, exit codes, changed files, path audit, and residual governance gaps.

## Risks and rollback

- Governance drift can activate blocked work or misrepresent contract/release authority; fail closed on ambiguity.
- Rollback restores task metadata only and must not alter business code or normative contracts.

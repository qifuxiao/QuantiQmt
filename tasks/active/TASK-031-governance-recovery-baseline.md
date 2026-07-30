---
id: TASK-031
title: Restore governance state and establish machine-verifiable recovery baseline
status: active
depends_on: [TASK-014]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/README.md
  - tasks/AGENTS.md
  - tasks/templates/task-template.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - tasks/governance-waivers.yaml
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
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

恢复任务、规范、实现、Review 与发布状态的一致性，并建立可机器验证的治理基线。本任务不改变业务代码、公开事件、DTO、Schema、Workflow 或其他规范契约。

## Non-goals

- 不实现 Risk、Strategy、Persistence 或任何业务运行时代码。
- 不修改 `spec/**`、`src/**`、`tests/**`（除获批的 validator test）、migrations 或 PR #40。
- 不虚构历史 Review、Approve、CI、merge 或 release 证据。

## Acceptance criteria

- [ ] 队列目录、front matter、`tasks/index.yaml` 与 active README 一致，且唯一 active task 为 TASK-031。
- [ ] Required governance state contract（`delivery.schema_version: 1`）机器可区分以下轴：front matter `status` 是唯一 `task_status`，值为 `blocked|ready|active|completed`，其中 `blocked|ready` 绑定 `backlog/`、`active` 绑定 `active/`、`completed` 绑定 `completed/`（全仓可有多个 active；治理冻结期间唯一 active 必须为 TASK-031）；`contract_status` 为 `not_applicable|draft|accepted|superseded`；`implementation_status` 为 `not_applicable|not_started|in_progress|merged`；`acceptance_status` 为 `not_run|partial|passed|unverified`；`review_status` 为 `not_required|pending|changes_requested|approved|reported_unverified`；`release_status` 为 `not_applicable|prohibited|eligible|released`。这些轴不得复用一个 status 字段表达。
- [ ] Completed 新任务必须满足 `acceptance_status=passed`、`review_status=approved|not_required`、`implementation_status=merged|not_applicable`；`reported_unverified` 必须 `release_status=prohibited`，且 `remediation_task` 或有效 waiver 非空，不得解锁依赖或成为 release evidence。
- [ ] Completion evidence 至少包含 `mode`、`change_pr`、`reviewed_head_sha`、review `verdict`/`reviewer`/`evidence_url`、`merge_commit_sha` 和 human authorization evidence；waiver 至少包含 `task_id`、`rule`、`reason`、`owner`、`expires_on`、`remediation_task`，且不得允许 `eligible|released`。
- [ ] 为 TASK-004/005/016/029/030 建立可审计 Evidence；无法证明的历史事实必须使用 `review_status=reported_unverified`、`release_status=prohibited` 和非空 remediation/有效 waiver，不得补造 APPROVE。
- [ ] 扩展 `validate_specs` 检查目录/status/index、active README、依赖激活门禁、completed criteria/evidence、上述 delivery 组合、completion evidence 格式、waiver 到期与禁止放行；测试覆盖正反例。任何 legacy gap 只能通过有效 waiver 登记，且不得解锁依赖或允许 release。
- [ ] 建立 OrderIntent→OMS→Risk→Outbox→Execution、Inbox/Event Backbone、Strategy/Market 责任矩阵。
- [ ] 建立 ADR-0008、Risk 去重、manifest/docs lifecycle、Strategy event activation 偏差清单，并派生后续任务建议；本任务不修改业务或规范契约。
- [ ] 所有验证通过，且无业务代码或契约变化。

## Governance authorization and evidence

- Human members explicitly authorized this governance freeze, unified task-state recovery, TASK-016 completion migration, TASK-029 blocking, and creation of this recovery task.
- PR #46 was closed before this task; its branch and commits are not reused and are not evidence.
- TASK-016 completion evidence is retained in its completed task file; TASK-029 is frozen until TASK-031 completion and independent Review.
- Human bootstrap authorization: owner `qfxyyy`, expires `2026-08-13`; the sole exception is `TASK-014 → TASK-031` for TASK-031 state recovery only. It has `one_time: true`, `deny_business_unlock: true`, and `release_status: prohibited`; it cannot unlock business work or authorize release. TASK-014 PR21 facts: head `29ab5b4457861bea0a4116c878b19987118bd9c4`, merge `96b5e5960f498da726b678ff6b0f0885b4ecdafd`, CI [run 29063208943/job/86269287092](https://github.com/qifuxiao/QuantiQmt/actions/runs/29063208943/job/86269287092) and [run 29063168140/job/86269165408](https://github.com/qifuxiao/QuantiQmt/actions/runs/29063168140/job/86269165408); GitHub review is unavailable, therefore review status is `reported_unverified` and these facts are not release evidence.

## Required evidence

- Record exact base/head/merge/review/release facts; mark every unproven historical claim `unverifiable`.
- Record validation commands, exit codes, changed files, path audit, and residual governance gaps.

## Risks and rollback

- Governance drift can activate blocked work or misrepresent contract/release authority; fail closed on ambiguity.
- Rollback restores task metadata only and must not alter business code or normative contracts.

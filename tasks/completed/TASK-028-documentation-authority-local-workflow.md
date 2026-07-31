---
id: TASK-028
title: Documentation authority, local environment, and team workflow cleanup
status: completed
depends_on: [TASK-014]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - README.md
  - .env.example
  - docs/README.md
  - docs/10-EventDriven/Event-Catalog.md
  - docs/10-EventDriven/Event-Payload-Catalog.md
  - docs/15-Interfaces/API-Contracts.md
  - docs/80-Deployment/Local-Development-Environment.md
  - ai/README.md
  - ai/workflows/team-collaboration.md
  - tasks/active/README.md
  - tasks/active/TASK-028-documentation-authority-local-workflow.md
  - tasks/index.yaml
  - docs/standards/01-Coding-Convention/01-Engineering-Convention-Part01.md
  - docs/standards/01-Coding-Convention/01-Engineering-Convention-Part02.md
  - docs/standards/01-Coding-Convention/01-Engineering-Convention-Part03.md
forbidden_paths:
  - src/**
  - tests/**
  - migrations/**
  - spec/contracts/**
  - spec/interfaces/**
  - spec/workflows/**
  - spec/state-machines/**
  - spec/storage/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: unverified
  review_status: reported_unverified
  release_status: prohibited
  remediation_task: TASK-031
  completion_evidence: {mode: historical_evidence_unverifiable, change_pr: unverifiable, reviewed_head_sha: unverifiable, review_verdict: reported_unverified, reviewer: unverifiable, evidence_url: unverifiable, merge_commit_sha: unverifiable, human_authorization_evidence: TASK-031 governance recovery authorization}
---

### Governance delivery evidence

Historical Review/CI/merge evidence is not independently verifiable; no approval is inferred.

# Objective

收敛第一优先级文档治理问题：更新根入口、明确 `docs/` 与 `spec/` 的权威边界、补齐本地 PostgreSQL/Poetry/Docker 环境说明，并把多成员三会话协作模式沉淀为工具无关流程。

## Non-goals

- 不修改业务代码、测试代码或数据库 migration。
- 不改变 Event、Command、DTO、状态机、Repository、Workflow 或错误码契约。
- 不移动 TASK-004、TASK-015 到 completed。
- 不处理 ADR 状态收敛、Runbook 集合或安全权限模型；这些属于后续文档治理任务。

## Acceptance criteria

- [x] 根 `README.md` 不再写死过期 Baseline/TASK 状态，并指向 `spec/manifest.yaml` 与 `tasks/index.yaml`。
- [x] `docs/10-EventDriven/Event-Catalog.md`、`Event-Payload-Catalog.md` 和 `docs/15-Interfaces/API-Contracts.md` 不再自称唯一规范来源，明确 `spec/` 为实现契约。
- [x] 新增本地开发环境文档，覆盖 Poetry fallback、Docker PostgreSQL 16、PowerShell/Git Bash 命令、`QUANTIQMT_POSTGRES_DSN` 和常见错误。
- [x] `.env.example` 包含本地 PostgreSQL integration test DSN 示例。
- [x] 新增多成员 AI Agent 团队协作文档，冻结协调/开发/Review 会话职责和交接格式。
- [x] `docs/README.md` 与 `ai/README.md` 链接新增文档。

## Evidence

- `README.md` 改为引用 `spec/manifest.yaml`、`tasks/index.yaml` 和 `tasks/active/README.md`，不再描述过期 Baseline/TASK 状态。
- `docs/10-EventDriven/Event-Catalog.md`、`docs/10-EventDriven/Event-Payload-Catalog.md` 和 `docs/15-Interfaces/API-Contracts.md` 均声明自身为解释性总览，规范性契约以 `spec/` 为准。
- `docs/80-Deployment/Local-Development-Environment.md` 新增 Poetry fallback、PostgreSQL 16 Docker、PowerShell/Git Bash DSN、TASK-004 验证和常见错误。
- `.env.example` 新增本地测试用 `QUANTIQMT_POSTGRES_DSN`。
- `ai/workflows/team-collaboration.md` 新增协调/开发/Review 三会话协作、跨成员 Review、指令模板和环境门槛。
- `docs/README.md` 与 `ai/README.md` 已链接新增文档。
- `poetry run python scripts/validate_specs.py`: passed。
- `poetry run pytest tests/spec tests/contract`: 192 passed。

### Authority follow-up evidence

- Independent post-merge review identified a P2 finding: the three Engineering Convention banners incorrectly treated `docs/README.md` L4 Catalog/Specification as authoritative for implementation contracts.
- Human project members explicitly authorized restoring TASK-028 from completed to active and adding exactly the three Engineering Convention files above to `allowed_paths`; TASK-005 remains active and isolated.
- Old PR #30, its branch, commit, and review are intentionally skipped and are not evidence for this follow-up.
- This change is rebuilt as a clean follow-up from the latest `origin/main`.
- TASK-028 remained active until the independent reviewer approved PR #35; this separate human-authorized migration records the resulting completed state.

### Completion evidence

- PR #35 Head `29e594f93d09d13dc0ef0af9efdff474a425ca5e` received an independent APPROVE and was merged into `main`.
- PR #35 merge commit / current `origin/main`: `7d013f3333c6fd61ed9da6611ef76e6738f06058`.
- CI passed 4/4; `tests/spec tests/contract` passed with 195 tests.
- This completed status migration is written under explicit human authorization; no document content or business code is changed by the migration.

## Required evidence

- `poetry run python scripts/validate_specs.py`
- `poetry run pytest tests/spec tests/contract`
- `git diff --name-status` 证明只修改 allowed paths。

## Risks and rollback

- 文档入口若继续漂移，会导致新成员或 AI Agent 误把解释性文档当成可实现契约。
- 回滚仅影响文档和任务元数据，不影响 runtime schema、持久化数据或业务代码。

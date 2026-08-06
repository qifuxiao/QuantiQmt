---
id: TASK-043
title: Restore governance trust and waiver lifecycle
status: active
depends_on: []
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/active/README.md
  - tasks/active/TASK-043-governance-trust-and-waiver-lifecycle.md
  - tasks/backlog/TASK-005-risk-engine.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/completed/TASK-014-implementation-readiness.md
  - tasks/completed/TASK-015-risk-contracts.md
  - tasks/completed/TASK-030-risk-validator-integration-scope.md
  - tasks/governance-waivers.yaml
  - tasks/index.yaml
  - scripts/validate_specs.py
  - tests/spec/test_validate_specs.py
  - ai/governance/**
forbidden_paths:
  - src/**
  - spec/**
  - docs/**
  - migrations/**
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
  - pyproject.toml
  - poetry.lock
  - .github/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec
    - poetry run mypy src scripts
    - poetry run ruff check scripts tests/spec
    - poetry run ruff format --check scripts tests/spec
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

Restore a machine-verifiable governance baseline so historical delivery evidence, dependency activation, and expiring bootstrap waivers cannot silently diverge again.

## Non-goals

- 不实现 Risk、Strategy、Persistence、Execution、Broker 或任何业务运行时代码。
- 不修改 `spec/**`、公开 Event/Command/DTO、错误码、状态机、Workflow 或数据库 migration。
- 不把无法独立证明的历史 Review、CI、merge 或 release 事实改写为已验证事实。
- 不激活 TASK-005、TASK-029 或其他业务任务。

## Deliverables

- 明确 bootstrap waiver 的 active、retired、expired 生命周期；到期或治理任务完成后，规范校验仍能 fail-closed 且不会留下永久例外。
- 统一 `ready`、`blocked` 与实际 dependency unlockable 的机器语义；不可激活任务不得仅因文本标记为 ready。
- 对 TASK-014、TASK-015、TASK-030 的历史交付证据进行可追溯核验；无法证明的事实保持 `reported_unverified`，不得补造批准。
- 扩展 `validate_specs.py` 及 `tests/spec/test_validate_specs.py` 的真实 `validate_tasks()` 集成覆盖。
- 同步 `ai/governance/**`、任务索引和 active projection，记录责任人、到期日、remediation 与剩余阻断。

## Acceptance criteria

- [ ] waiver 在有效期内、到期后、退休后和重复登记时均有明确且机器可验证的结果；不会因历史 bootstrap 例外导致规范门禁永久失败或允许业务解锁。
- [ ] `ready` 任务的依赖可信度有明确语义；任何 `reported_unverified` 或缺失 delivery 的依赖都不能激活下游任务。
- [ ] TASK-014、TASK-015、TASK-030 的 evidence 只接受可追溯 PR/head/review/merge/human authorization；未知事实仍写作 `unverifiable`。
- [ ] 负例通过真实 `validate_tasks()` 路径覆盖：过期 waiver、重复 waiver、错误 beneficiary、缺失 evidence、reported_unverified 依赖和伪 ready 任务。
- [ ] TASK-005、TASK-029 仍保持 blocked；本任务不解锁、不发布任何业务能力。
- [ ] 所有 verification.commands 通过，且 allowed/forbidden path 审计无越权。

## Required evidence

- 记录 waiver 生命周期决策、历史证据核验结果、任务状态迁移、精确 Base/Head、Review 与 CI 证据。
- 每条 acceptance criterion 提供命令、fixture 或 GitHub 事实；不得用测试全绿替代历史 Review 证据。

## Governance evidence

- TASK-031 completed on main, so its one-time TASK-014 bootstrap exception is retired on 2026-08-05. Retired and expired records remain auditable but cannot unlock dependencies or release capability.
- `ready` is a backlog candidate label only. Actual activation requires every dependency to have trusted completed delivery; neither `ready` nor `blocked` bypasses that machine gate.
- TASK-014, TASK-015, and TASK-030 PR/head/merge facts were reconstructed from local Git objects on 2026-08-06. GitHub Review/CI queries could not be authenticated or reached, so unknown Review, CI, and human-authorization facts remain `reported_unverified` / `unverifiable` and release remains prohibited.
- TASK-005 and TASK-029 remain blocked. This task authorizes no business activation or release.

## Risks and rollback

- 若 waiver 生命周期或历史证据无法安全解释，保持所有业务任务 blocked，不能延长例外或绕过依赖门禁。
- 回滚只恢复治理元数据和验证器行为，不得改变业务代码、公开契约或持久化数据。

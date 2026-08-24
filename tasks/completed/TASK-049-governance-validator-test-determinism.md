---
id: TASK-049
title: Make governance waiver validation tests deterministic and cleanup-safe
status: completed
depends_on: [TASK-043]
spec_refs: [REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths:
  - tasks/backlog/TASK-049-governance-validator-test-determinism.md
  - tasks/active/TASK-049-governance-validator-test-determinism.md
  - tasks/completed/TASK-049-governance-validator-test-determinism.md
  - tasks/active/README.md
  - tasks/completed/README.md
  - tasks/index.yaml
  - scripts/validate_specs.py
  - tests/spec/test_validate_specs.py
forbidden_paths:
  - tasks/governance-waivers.yaml
  - spec/**
  - src/**
  - docs/**
  - migrations/**
  - tests/contract/**
  - tests/unit/**
  - tests/property/**
  - tests/integration/**
  - .github/**
  - pyproject.toml
  - poetry.lock
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec/test_validate_specs.py
    - poetry run pytest tests/unit tests/property tests/spec tests/contract --cov --cov-report=term-missing
    - poetry run mypy scripts
    - poetry run ruff check scripts/validate_specs.py tests/spec/test_validate_specs.py
    - poetry run ruff format --check scripts/validate_specs.py tests/spec/test_validate_specs.py
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: governance_closeout_after_approved_review
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/77
    reviewed_head_sha: 70bfc569b06a093bfa22e53bb840a8a982465f61
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/77#pullrequestreview-5005677302
    merge_commit_sha: 5c6ed3769babfd6a4b1c4eba990de50662ce0fc1
    human_authorization_evidence: 2026-08-24 user authorized TASK-049 activation and implementation, then confirmed PR #77 merged for closeout
---

# Objective

Make governance waiver validation and its tests independent of wall-clock drift and repository-shared fixture cleanup, while preserving the existing fail-closed waiver lifecycle.

## Non-goals

- 不延长、重新激活、替换或删除 2026-08-13 到期的 bootstrap waiver。
- 不修改 `tasks/governance-waivers.yaml`，不改变 TASK-014、TASK-031 或 TASK-043 的历史状态和证据。
- 不修改 TASK-022 的控制面契约，不把 TASK-022 或任何下游业务任务标记 completed、eligible 或 released。
- 不修改业务代码、公开 Event/Command/DTO、状态机、Workflow、数据库或 CI 配置。

## Deliverables

- 为 waiver dependency 判定提供显式、可测试的评估日期，并确保同一次 `validate_tasks()` 运行使用同一日期快照；生产默认行为仍使用当前日期并保持 fail-closed。
- 将依赖真实日期的 bootstrap 正反例改为固定日期输入，覆盖到期前允许、到期后拒绝、retired/expired 拒绝，禁止用新的远期常量掩盖问题。
- 移除 `tests/spec/test_validate_specs.py` 对仓库内共享 `tasks/.validator-fixture` 的脆弱依赖；每个测试使用独立临时目录或等价隔离，并在断言失败时也不留下文件。
- 增加回归覆盖，证明一个用例失败或中断不会令后续用例因目录非空而级联失败。

## Acceptance criteria

- [x] `bootstrap_allows_dependency` 的测试不读取测试运行当天日期；2026-08-13 后运行仍稳定，且显式到期场景始终拒绝。
- [x] `validate_tasks()` 在一次运行内复用同一评估日期，waiver 校验与 dependency unlock 判定不会因跨日产生分歧。
- [x] 所有写文件的 validator 测试使用独立临时路径或 `try/finally` 等价保护；测试失败后仓库内不存在 `tasks/.validator-fixture` 残留。
- [x] 2026-08-13 bootstrap waiver 保持 retired、release prohibited，且 TASK-014→TASK-031 之外的依赖仍不能获得例外。
- [x] PR #76 中观察到的 2 个日期相关失败和 4 个 cleanup 级联失败均由针对性回归测试覆盖。
- [x] 所有 verification.commands 通过，allowed/forbidden path 审计无越权。

## Required evidence

- 记录失败复现、固定日期边界用例、fixture 隔离回归、完整测试结果和变更文件。
- 记录精确 Base/Head、独立 Review verdict/evidence、PR、merge commit 和人类 closeout 授权；未核验事实保持 `unverifiable`。

## Risks and rollback

- 若显式日期注入削弱生产 fail-closed 行为或允许过期/terminal waiver 解锁，立即停止并保持 TASK-049 未完成。
- 回滚仅恢复 validator 的日期传递和测试 fixture 结构；不得改变 waiver 注册表、业务任务状态或规范契约。

## Closeout evidence

- PR #77 was formally approved by `qfxyyy` on exact head `70bfc569b06a093bfa22e53bb840a8a982465f61` and merged into `main` as `5c6ed3769babfd6a4b1c4eba990de50662ce0fc1`.
- GitHub reports all four checks passed. Independent Review reported no P0/P1/P2/P3 findings and verdict `APPROVE`.
- Implementation verification passed: specification validation; 45 targeted spec tests; 691 full unit/property/spec/contract tests at 85% coverage; mypy; Ruff check/format; pre-commit; and `git diff --check`.
- TASK-049 closes only the governance validator determinism defect. Release remains prohibited, and no business task or capability is unlocked by this closeout.

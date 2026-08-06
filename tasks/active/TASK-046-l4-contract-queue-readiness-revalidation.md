---
id: TASK-046
title: Revalidate implementation readiness for the L4 contract queue
status: active
depends_on: []
spec_refs:
  - REVIEW-IMPLEMENTATION-READINESS-0.5
allowed_paths:
  - tasks/active/TASK-046-l4-contract-queue-readiness-revalidation.md
  - tasks/active/README.md
  - tasks/index.yaml
  - spec/manifest.yaml
  - spec/reviews/**
  - tasks/backlog/TASK-017-execution-broker-contracts.md
  - tasks/backlog/TASK-018-ledger-portfolio-contracts.md
  - tasks/backlog/TASK-019-target-resolver-contracts.md
  - tasks/backlog/TASK-020-market-data-contracts.md
  - tasks/backlog/TASK-021-backtest-live-parity-contracts.md
  - tasks/backlog/TASK-022-observability-control-contracts.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tests/spec/**
  - scripts/validate_specs.py
  - ai/governance/**
forbidden_paths:
  - src/**
  - migrations/**
  - docs/**
  - tasks/completed/**
  - tasks/governance-waivers.yaml
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
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: not_applicable
  implementation_status: in_progress
  acceptance_status: partial
  review_status: pending
  release_status: prohibited
---

# Objective

在当前 accepted spec、Accepted ADR、当前任务队列和当前实现状态上，重新执行可机器验证、可独立 Review 的实施就绪评审，为 TASK-017、TASK-018、TASK-020、TASK-022 及其下游 L4 契约任务建立新的可信依赖门禁。

## Scope and deliverables

- 重新读取并以当前全部 accepted spec、Accepted ADR、任务依赖和实现状态为评审基线，不沿用历史结论替代当前证据。
- 逐项重新评审 TASK-017、TASK-018、TASK-019、TASK-020、TASK-021、TASK-022、TASK-029 的 L4 可实施性，包括契约完整性、依赖可信度、失败路径、验证范围和解除条件。
- 新建 `REVIEW-IMPLEMENTATION-READINESS-0.7`，注册到 `spec/manifest.yaml`，并保留 `REVIEW-IMPLEMENTATION-READINESS-0.5` 原文、ID 和历史状态不变。
- 对每个被评审任务给出明确、可复验的 `ready` 或 `blocked` 结论；blocked 结论必须列出具体缺口、可信依赖和解除条件。
- 仅当新评审判定 TASK-017、TASK-018、TASK-020、TASK-022 已具备 L4 可实施性时，才把相应任务对 TASK-014 的治理依赖迁移到 successor TASK-046，并同步任务文件与 `tasks/index.yaml`；迁移不得表述或暗示 TASK-014 获得过历史批准。
- 对 TASK-019、TASK-021 的当前 L4 可实施性和下游门禁单独给出结论；不得仅因上游任务通过而自动标记 ready 或解除其他依赖。
- 对 TASK-029 基于 TASK-030 的 `reported_unverified` 状态单独判断；TASK-046 不得替代、豁免或顺带修复 TASK-030 的证据缺口。
- 更新 validator 与 spec tests，机器证明 `reported_unverified` 或缺失可信 delivery evidence 的依赖不能激活下游任务；对应任务只有在 TASK-046 完成且具有可信 completion/delivery evidence 后，才可能通过依赖激活门禁。
- 在 `ai/governance/**` 记录评审基线、逐任务判定、validator 证据、精确 Base/Head 和剩余阻断，供独立 Review 复验。

## Non-goals and invariants

- 不执行任何业务或 L4 契约实现，不激活 TASK-017、TASK-018、TASK-019、TASK-020、TASK-021、TASK-022、TASK-029 或其下游业务任务。
- 不修改任何业务 Event、Command、DTO、错误码、状态机、Workflow、Repository 契约或运行时代码。
- TASK-014 必须继续保持 `review_status: reported_unverified`、`release_status: prohibited`；不得补造、推断或改写其历史 Review、批准或交付证据。
- retired waiver 必须保持 retired；不得使用、恢复、延长、扩展或复制 waiver 来解锁业务或 L4 契约任务。
- TASK-030 的 `reported_unverified` 状态不得被 TASK-046 或 TASK-031 的可信证据替代；TASK-029 必须继续 fail-closed，除非其全部直接依赖分别取得可信完成证据。
- TASK-046 实现 Agent 不得自行批准 Review、添加完成证据、将本任务从 active 迁移到 completed，或执行任何被评审任务；所有变更必须由独立 Review 验证后再由人类授权收尾。

## Acceptance criteria

- [x] 当前全部 accepted spec、Accepted ADR、任务依赖和相关实现状态均被重新读取，评审记录可定位到精确仓库 Base/Head。
- [x] `REVIEW-IMPLEMENTATION-READINESS-0.7` 是新的当前版本 Implementation Readiness Review，具有唯一规范 ID 并登记在 `spec/manifest.yaml`；历史 `REVIEW-IMPLEMENTATION-READINESS-0.5` 未被覆盖或改写。
- [x] TASK-017、TASK-018、TASK-019、TASK-020、TASK-021、TASK-022、TASK-029 均有逐项、证据化、可独立复验的 L4 可实施性结论，以及明确的 ready/blocked 状态和解除条件。
- [x] TASK-014 仍为 `reported_unverified` 且 release prohibited；没有历史批准、Review、CI 或授权事实被补造或提升为可信证据。
- [x] retired waiver 未被使用、恢复、延长、扩展、复制或用于任何业务/L4 解锁。
- [x] 只有经新评审确认具备 L4 可实施性的 TASK-017、TASK-018、TASK-020、TASK-022，才把治理依赖从 TASK-014 迁移到 TASK-046；未通过者保持 blocked，并记录精确解除条件。
- [x] TASK-019 与 TASK-021 的状态按自身契约和全部直接依赖分别判定，没有因上游结论而自动解锁。
- [x] TASK-029 根据 TASK-030 的 `reported_unverified` 状态单独判定，未被 TASK-046 顺带解锁或替换其 remediation 路径。
- [x] validator 与 `tests/spec/**` 的正反例证明：`reported_unverified`/缺失可信 delivery evidence 的依赖拒绝激活；active/in-progress 的 TASK-046 也不能解锁对应任务；只有 completed TASK-046 的可信 delivery/completion evidence 才能满足 successor 门禁。
- [x] `poetry run python scripts/validate_specs.py` 与 `poetry run pytest tests/spec tests/contract` 全部通过，且变更路径审计未超出 allowed paths、未触及 forbidden paths。
- [x] 没有业务 Event、Command、DTO、错误码、状态机、Workflow、Repository 契约、运行时代码或业务发布能力发生变化。
- [ ] TASK-046 的实现结果已经独立 Review；实现 Agent 未自行批准、补写完成证据或执行 active-to-completed 状态迁移。

## Implementation evidence pending independent Review

- Audited base is `f50d471530fe355e17e7ce82a33a24b8c1b2c01f`; the implementation branch is `codex/task-046-readiness-revalidation`. The exact pushed PR head is reported at handoff and must be the SHA bound by independent Review.
- `REVIEW-IMPLEMENTATION-READINESS-0.7` and `ai/governance/l4-readiness-revalidation-task-046.yaml` record the accepted spec/ADR inventory, implementation baseline, seven decisions, dependency before/after matrix and remaining blockers.
- TASK-017/018/020/022 remain backlog/ready and now depend on TASK-046. TASK-019/021 remain backlog/blocked with all other direct dependencies retained. TASK-029 remains backlog/blocked on TASK-030 and does not depend on TASK-046.
- Validator integration covers TASK-046 active/in-progress, completed/reported-unverified, completed/missing evidence and completed/trusted evidence; only the last satisfies the dependency gate and none auto-activates a task.
- `poetry run python scripts/validate_specs.py` passed. `poetry run pytest tests/spec tests/contract` passed with 229 tests; the only warning is inability to create `.pytest_cache` under workspace permissions.
- No completion evidence, approval, merge claim, release eligibility or active-to-completed transition is recorded by the implementing Agent. The final acceptance item remains open for independent Review and human-authorized closeout.

## Required evidence

- 新评审必须记录 accepted spec/ADR 清单、任务与实现基线、逐任务判定矩阵、每个 blocked 条目的解除条件，以及精确 Base/Head。
- 依赖迁移必须提供新旧 `depends_on` 对照，并证明没有把 TASK-014 的历史状态改写为 approved。
- validator 证据必须覆盖 `reported_unverified`、缺失 evidence、TASK-046 active/in-progress 和 TASK-046 completed/trusted 四类状态。
- 最终报告必须列出修改文件、verification 命令及结果、仍被阻塞的任务、规范偏差和未解决风险。
- 完成证据必须包含 change PR、reviewed head SHA、独立 Review verdict/reviewer/evidence URL、merge commit SHA 和人类收尾授权；未知事实必须保持 `unverifiable`。

## Independent Review focus

- 复验评审是否基于当前 accepted spec/ADR/实现，而不是复述或洗白历史 `REVIEW-IMPLEMENTATION-READINESS-0.5`。
- 逐项核对 TASK-017/018/019/020/021/022/029 的 L4 结论、依赖迁移、解除条件和 validator fixtures 是否一致且 fail-closed。
- 核对 TASK-014、TASK-030 与 retired waiver 均未被提升、恢复或用作业务解锁证据。
- 核对实现 Agent 未自批 Review、未自行完成 TASK-046、未激活任何被评审任务。

## Risks and rollback

- 若当前规范、实现或依赖证据存在歧义，相关任务保持 blocked；不得用 ready 标签、历史叙述或 waiver 代替可信完成证据。
- 回滚只能恢复本任务产生的评审、治理元数据、任务依赖和 validator/spec-test 变更；不得改变历史 Review、业务代码、公开契约、持久化数据或 waiver 生命周期。

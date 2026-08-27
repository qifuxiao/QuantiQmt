---
id: TASK-050
title: Freeze OrderRegistration broker binding persistence compatibility contracts
status: active
depends_on: [TASK-017]
spec_refs: [INV-TRADING, INV-CONSISTENCY, PORTS-CORE, PORTS-ORDER-PERSISTENCE, REPO-ORDER, STORAGE-SOT, STORAGE-ORDER-PERSISTENCE, WF-ORDER-COMMIT, WF-RECOVERY, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, NFR-RELIABILITY, CONTRACT-EXECUTION-BROKER-GATEWAY-V1]
allowed_paths:
  - spec/manifest.yaml
  - spec/interfaces/core-ports.md
  - spec/interfaces/order-persistence-ports.md
  - spec/repositories/order-repository.md
  - spec/storage/order-persistence.yaml
  - spec/workflows/order-commit.yaml
  - spec/workflows/recovery.yaml
  - spec/workflows/submit-order.yaml
  - spec/workflows/cancel-order.yaml
  - spec/nfr/reliability.yaml
  - tests/spec/test_order_registration_binding_contracts.py
  - tests/contract/messages/test_backtest_live_parity_contracts.py
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
  - tasks/active/TASK-050-order-registration-binding-contracts.md
  - tasks/completed/TASK-050-order-registration-binding-contracts.md
  - tasks/active/README.md
  - tasks/index.yaml
forbidden_paths: [src/**, migrations/**, tests/unit/**, tests/property/**, tests/integration/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec
    - poetry run pytest tests/contract
    - poetry run ruff check tests/spec/test_order_registration_binding_contracts.py
    - poetry run ruff format --check tests/spec/test_order_registration_binding_contracts.py
delivery:
  schema_version: 1
  contract_status: draft
  implementation_status: in_progress
  acceptance_status: passed
  review_status: pending
  release_status: prohibited
---

# Objective

冻结 `OrderRegistration` 的 broker/capability binding、legacy unbound、PostgreSQL expand-only migration、Journal/Snapshot 兼容读取及恢复 fail-closed 契约，使 TASK-048 无需自行发明 DTO、存储或恢复语义。

## Activation evidence

- 2026-08-27 人类明确授权创建、激活并实施 TASK-050。
- 2026-08-27 人类追加授权精确修改 `tests/contract/messages/test_backtest_live_parity_contracts.py`，仅用于把全局 manifest `0.13.0`/previous-version 硬编码改为最低兼容版本断言；不授权修改 Backtest schema、fixture 或业务语义。
- TASK-017 已可信 completed 并冻结 submit/cancel 的五项 broker binding guard，但未冻结 legacy unbound 的存储与恢复表示。TASK-004 是既有实现基线，不作为本规范任务的 trusted delivery 依赖。
- 本任务不授权 runtime、migration、Broker dispatch、TASK-048 激活、部署、发布或 active → completed closeout。

## Non-goals

- 不实现 TASK-048 runtime 或 SQL migration。
- 不新增公开 Event/Command、错误码或 Order 状态迁移。
- 不提供历史 registration 绑定修复入口；任何未来修复必须由独立、可审计的 reconciliation/spec-change task 冻结。
- 不回填或推断任何历史 broker/capability identity。

## Acceptance criteria

- [x] 冻结 BOUND 与 legacy UNBOUND 的唯一 runtime/serialized/storage 表示，禁止半绑定。
- [x] 冻结新 registration 必须 BOUND、legacy UNBOUND 只读兼容以及 submit/cancel fail-closed 语义。
- [x] 冻结两个 nullable additive PostgreSQL 列、成对约束、不可变约束、无回填 migration 和混合版本部署顺序。
- [x] 冻结旧 Journal/Snapshot 原始 checksum 不重写、缺失字段按 UNBOUND 读取、新记录完整写入绑定及 projection/replay 一致性。
- [x] 明确 TASK-048 不得绑定历史数据，未来 repair 需要独立审核契约和追加式审计事实。
- [x] 更新 manifest 版本、兼容性、迁移、回滚、受影响任务与 TASK-048 依赖。
- [x] 提供机器测试覆盖 binding 状态矩阵、storage 列/约束、recovery、workflow guard、manifest 与 task handoff。

## Implementation evidence

- `OrderRegistration` 冻结为 `BOUND(non-null, non-null)` 与 legacy `UNBOUND(null, null)` 两态；半绑定在任何 Repository、Journal、Snapshot、Outbox 或 Broker 副作用前失败。
- `STORAGE-ORDER-PERSISTENCE` 冻结两个 nullable additive projection 列、complete-or-unbound/trimmed-bound checks、插入后不可变、禁止历史回填和 expand-only rollout/rollback 顺序。
- 新 registration 必须在事务前 BOUND；legacy 缺字段或 null pair 只在原始 Journal/Snapshot checksum 验证后解析为 UNBOUND，禁止注入 null 后重新 canonicalize，projection/rebuild 只能以 Journal 为权威。
- submit/cancel 对 UNBOUND 在 dispatch 前 fail closed；Recovery 保留 UNBOUND、保持 SAFE 并要求 reconciliation evidence。TASK-048 不提供 rebinding，未来修复需要独立审核的追加式 repair contract。
- manifest 升级到 `0.14.0`，公开消息与错误码不变；TASK-048 增加 TASK-050 trusted closeout 依赖并继续 blocked。
- 经追加人类授权，Backtest 既有契约测试仅把全局 manifest 精确版本硬编码替换为 `>= 0.13.0` 最低兼容断言，未修改 Backtest schema、fixture 或业务语义。

## Verification evidence

- `poetry run python scripts/validate_specs.py`：通过。
- `poetry run pytest tests/spec -q`：`51 passed`。
- `poetry run pytest tests/contract -q`：`666 passed`。
- focused binding/Backtest compatibility：`54 passed`。
- `poetry run ruff check` 与 `poetry run ruff format --check`：两个变更测试文件通过。
- `git diff --check`：通过。

## Handoff boundary

- 本地 acceptance 已通过；contract 仍为 draft、implementation 仍为 in_progress、Review 为 pending，等待另一位成员对精确 Head 独立 Review。
- 未实现 runtime、SQL migration、PostgreSQL/Docker 验证、Broker dispatch、deployment 或 release；这些仍属于 Review/closeout 后另行激活的 TASK-048。

## Review focus

- legacy 数据是否始终 unbound/fail-closed，且没有 sentinel、默认 Broker 或 ambient capability 推断。
- 新写入是否必须完整绑定，半绑定是否在 DTO、serialization、projection 与 migration 各层失败。
- 旧 Journal/Snapshot checksum 是否保持原样，恢复是否不会把新字段注入旧事实。
- migration/rollback 是否 expand-only、可重复执行并保留历史与审计证据。

## Risks and rollback

- 绑定语义错误会使订单被错误路由到 Broker；任何缺失、矛盾或无法验证的绑定必须保持 UNBOUND/SAFE。
- 规范尚未被 runtime 采用前，可只回退本任务新增的规范与测试；采用后必须先停止 writer/dispatch，并永久保留已写入绑定、Journal、Snapshot 与审计证据。

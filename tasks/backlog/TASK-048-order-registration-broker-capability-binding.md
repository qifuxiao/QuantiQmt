---
id: TASK-048
title: Bind OrderRegistration persistence to broker capability versions
status: blocked
depends_on: [TASK-004, TASK-017]
spec_refs: [INV-TRADING, INV-CONSISTENCY, PORTS-CORE, PORTS-ORDER-PERSISTENCE, REPO-ORDER, STORAGE-SOT, STORAGE-ORDER-PERSISTENCE, WF-ORDER-COMMIT, WF-RECOVERY, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, NFR-RELIABILITY, CONTRACT-EXECUTION-BROKER-GATEWAY-V1]
allowed_paths:
  - src/quantiqmt/order/application/persistence/model.py
  - src/quantiqmt/order/application/persistence/serialization.py
  - src/quantiqmt/order/application/persistence/__init__.py
  - src/quantiqmt/order/infrastructure/memory.py
  - src/quantiqmt/order/infrastructure/postgres.py
  - migrations/002_order_registration_broker_capability.sql
  - tests/unit/order/application/test_persistence_model.py
  - tests/contract/persistence/test_order_persistence_contract.py
  - tests/integration/persistence/test_postgres_order_persistence.py
  - tests/integration/persistence/test_migration_and_ci_contract.py
  - tasks/backlog/TASK-048-order-registration-broker-capability-binding.md
forbidden_paths:
  - spec/**
  - src/quantiqmt/order/domain/**
  - src/quantiqmt/execution/**
  - src/quantiqmt/simulation/**
  - src/quantiqmt/live/**
  - tests/contract/messages/**
verification:
  commands:
    - poetry run pytest tests/unit/order/application/test_persistence_model.py
    - poetry run pytest tests/contract/persistence/test_order_persistence_contract.py
    - poetry run pytest tests/integration/persistence/test_postgres_order_persistence.py tests/integration/persistence/test_migration_and_ci_contract.py
    - poetry run mypy src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure
    - poetry run ruff check src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure tests/unit/order/application/test_persistence_model.py tests/contract/persistence/test_order_persistence_contract.py tests/integration/persistence
    - poetry run ruff format --check src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure tests/unit/order/application/test_persistence_model.py tests/contract/persistence/test_order_persistence_contract.py tests/integration/persistence
---

# Objective

实现 `OrderRegistration` 对选定 `broker` 与不可变 `broker_capability_version` 的持久化绑定，使 runtime DTO、canonical serialization、Memory/PostgreSQL projection、Journal、Snapshot 与 Recovery 使用同一绑定语义，并为历史 registration 提供可审计、fail-closed 的兼容路径。

## Blocking reason

TASK-048 必须保持 blocked，直到 TASK-017 完成独立 Review、合并及可信 closeout。TASK-017 只负责冻结契约与交付计划；TASK-048 才能在该冻结版本上实施 persistence/runtime compatibility。TASK-004 提供既有 Order persistence、Journal、Snapshot、Recovery 与 migration 基线。

在激活前必须确认 TASK-017 已冻结历史 unbound 表示、审计来源或人类授权绑定语义，以及 submit/cancel 的 fail-closed 边界。若这些契约仍不完整，必须先创建并评审独立 spec-change task；TASK-048 不得自行发明 Repository、Workflow、Event、DTO、错误码或状态迁移契约。

## Scope and deliverables

- 将新 registration 的 `broker` 与 `broker_capability_version` 作为同一注册提交中的不可变绑定证据持久化。
- 保持 runtime DTO、serialization payload、Memory 与 PostgreSQL projection、Journal post-state、Snapshot 和 Recovery/rebuild 结果一致。
- 提供 expand-only、可重复执行、失败安全的 `002_order_registration_broker_capability.sql`；历史行不得被当前 capability 状态自动回填。
- 将历史缺失字段的数据恢复为明确 unbound，并保持 submit/cancel fail-closed，直到存在可审计来源或人类授权的绑定证据。
- 记录 rollout、兼容读写、恢复演练与 rollback 证据；rollback 只能停止或回退 writer/reader，不得删除已写入的绑定或审计证据。

## Path audit and implementation boundary

- 建议的四个 persistence 测试文件均真实存在；`src/quantiqmt/order/application/persistence/__init__.py` 也真实存在。
- `migrations/002_order_registration_broker_capability.sql` 当前不存在，是本任务预期新增文件；现有基线为 `migrations/001_order_persistence_outbox.sql`。
- 当前 allowed paths 足以覆盖 persistence DTO、payload、Memory/PostgreSQL、migration 及 unit/contract/integration evidence，但不允许实现 Broker dispatch 或新增绑定授权 Port。submit/cancel dispatch 由依赖 TASK-048 的 TASK-006 实现；TASK-048 必须提供无法被 ambient/current capability 绕过的 bound/unbound persistence 结果。
- 若完成可审计历史绑定需要修改未列出的 Port、Workflow、Event、DTO 或错误码契约，必须停止并报告路径/契约不足，不得自行扩大到无关模块。

## Non-goals

- 不执行或修改 TASK-017 的正文、状态、Review 或完成证据。
- 不实现 Execution、Broker Simulator、MiniQMT adapter 或任何 Broker 副作用。
- 不修改公开 Event/Command、Order domain 状态机、Repository/Workflow 契约或错误码。
- 不盲目回填历史 registration，不用 adapter 当前 capability 状态替代持久化绑定。
- 不激活 TASK-048 或 TASK-006，不标记任何 acceptance criterion passed。

## Acceptance criteria

- [ ] `OrderRegistration` 持久化 `broker` 与 `broker_capability_version`，且绑定在注册后不可变。
- [ ] Memory、PostgreSQL、serialization、Journal、Snapshot 与 Recovery/rebuild 的绑定和 unbound 语义一致。
- [ ] 所有新写入 registration 必须包含完整、已验证的 broker 绑定信息；缺失任一字段时原子注册失败且无部分写入。
- [ ] 历史缺失字段的数据保持明确 unbound/fail-closed，不得使用当前或 ambient capability 状态盲目回填。
- [ ] 只有具备可审计来源的对账证据或明确人类授权才能完成历史绑定，且来源、授权和结果可追溯。
- [ ] Migration 必须 expand-only、可重复执行、失败安全，并支持旧 reader/new writer 与 new reader/old rows 的受控兼容阶段。
- [ ] Rollback 不得 DROP、DELETE、清空或覆盖已写入的 broker 绑定、授权记录、Journal、Snapshot 或恢复证据。
- [ ] registration 未绑定或绑定不完整时，submit/cancel 必须 fail-closed，且不得进入 Broker dispatch；不得从当前 adapter capability 旁路补值。
- [ ] 单元、persistence contract、PostgreSQL integration 与 migration tests 提供 DTO、payload、读写、历史行、Journal/Snapshot/Recovery、幂等 migration、rollout 和 rollback 验收证据。

## Review focus

- 历史数据是否始终 unbound/fail-closed，且不存在静默默认值、当前 capability 回填或 Broker dispatch 旁路。
- registration projection、Journal post-state、Snapshot 与 full-Journal rebuild 是否保持相同绑定证据。
- migration 是否仅扩展、可重入、失败安全，并保留所有历史与回滚审计证据。
- 绑定修复是否只能由已冻结的可审计对账来源或人类授权触发，且没有新增未评审契约。

## Risks and rollback

- 混合版本部署期间，旧数据和旧 writer 可能缺少绑定；门禁必须保持关闭，直到兼容读写和恢复演练证明安全。
- 任何绑定来源不明确、Journal/Snapshot 不一致或 migration 部分失败都必须保持 unbound/SAFE，并进入对账或人工处理。
- Rollback 只能停止新 writer、恢复上一兼容 reader 并保留新增列、绑定值和审计证据；禁止破坏性降级。

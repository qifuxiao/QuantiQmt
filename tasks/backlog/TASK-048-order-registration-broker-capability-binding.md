---
id: TASK-048
title: Bind OrderRegistration persistence to broker capability versions
status: blocked
depends_on: [TASK-004, TASK-017, TASK-050]
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

实现新 `OrderRegistration` 对选定 `broker` 与不可变 `broker_capability_version` 的持久化绑定，使 runtime DTO、canonical serialization、Memory/PostgreSQL projection、Journal、Snapshot 与 Recovery 使用同一绑定语义，并将历史 registration 仅作为永久 `UNBOUND`、fail-closed 的兼容数据读取。

## Blocking reason

TASK-048 必须保持 blocked，直到 TASK-017 与 TASK-050 均完成独立 Review、合并及可信 closeout。TASK-017 冻结 Execution/Broker 契约；TASK-050 冻结 legacy unbound、storage/migration 与 Journal/Snapshot 兼容语义；TASK-048 才能在该冻结版本上实施 persistence/runtime compatibility。TASK-004 提供既有 Order persistence、Journal、Snapshot、Recovery 与 migration 基线。

在激活前必须确认 TASK-050 已冻结历史 `UNBOUND` 表示、TASK-048 禁止 legacy rebinding，以及 submit/cancel 的 fail-closed 边界。若这些契约仍不完整，必须先创建并评审独立 spec-change task；TASK-048 不得自行发明 Repository、Workflow、Event、DTO、错误码、状态迁移或历史绑定契约。

## Scope and deliverables

- 将新 registration 的 `broker` 与 `broker_capability_version` 作为同一注册提交中的不可变绑定证据持久化。
- 保持 runtime DTO、serialization payload、Memory 与 PostgreSQL projection、Journal post-state、Snapshot 和 Recovery/rebuild 结果一致。
- 提供 expand-only、可重复执行、失败安全的 `002_order_registration_broker_capability.sql`；历史行不得被当前 capability 状态自动回填。
- 将历史缺失字段或 `(null, null)` 的数据恢复为明确 `UNBOUND`，并永久保持 submit/cancel fail-closed；TASK-048 期间 legacy `(null, null)` 永久保持 `UNBOUND`。
- legacy `UNBOUND` 不得通过对账证据、人工授权、当前 adapter、ambient capability 或任何旁路改成 `BOUND`。
- 任何未来历史绑定必须由独立 reviewed repair contract/task 承担；该未来工作不属于 TASK-048。
- 记录 rollout、兼容读写、恢复演练与 rollback 证据；rollback 只能停止或回退 writer/reader，不得删除已写入的绑定或审计证据。

## Path audit and implementation boundary

- 建议的四个 persistence 测试文件均真实存在；`src/quantiqmt/order/application/persistence/__init__.py` 也真实存在。
- `migrations/002_order_registration_broker_capability.sql` 当前不存在，是本任务预期新增文件；现有基线为 `migrations/001_order_persistence_outbox.sql`。
- 当前 allowed paths 足以覆盖新 registration 的 persistence DTO、payload、Memory/PostgreSQL、migration 及 unit/contract/integration evidence，但不允许实现 Broker dispatch、legacy rebinding 或绑定授权 Port。submit/cancel dispatch 由依赖 TASK-048 的 TASK-006 实现；TASK-048 必须提供无法被 ambient/current capability 或其他旁路改写的 bound/unbound persistence 结果。
- 若实现需要把任何 legacy `UNBOUND` 改成 `BOUND`，必须停止并报告超出 TASK-048；不得自行扩大 Port、Workflow、Event、DTO、错误码或任务边界。

## Non-goals

- 不执行或修改 TASK-017 的正文、状态、Review 或完成证据。
- 不实现 Execution、Broker Simulator、MiniQMT adapter 或任何 Broker 副作用。
- 不修改公开 Event/Command、Order domain 状态机、Repository/Workflow 契约或错误码。
- 不回填、修复或绑定任何历史 registration；对账证据、人工授权、当前 adapter、ambient capability、配置、Broker observation 或其他旁路均不得改变 legacy `UNBOUND`。
- 不定义或实现未来历史绑定；它必须由独立 reviewed repair contract/task 冻结证据、授权、追加式事实、幂等/CAS、UNKNOWN 与 rollback 语义。
- 不激活 TASK-048 或 TASK-006，不标记任何 acceptance criterion passed。

## Acceptance criteria

- [ ] `OrderRegistration` 持久化 `broker` 与 `broker_capability_version`，且绑定在注册后不可变。
- [ ] Memory、PostgreSQL、serialization、Journal、Snapshot 与 Recovery/rebuild 的绑定和 unbound 语义一致。
- [ ] 所有新写入 registration 必须包含完整、已验证的 broker 绑定信息；缺失任一字段时原子注册失败且无部分写入。
- [ ] 历史缺失字段或 `(null, null)` 永久保持明确 `UNBOUND`/fail-closed；TASK-048 不提供任何从 legacy `UNBOUND` 到 `BOUND` 的状态迁移或写入口。
- [ ] 对账证据、人工授权、当前 adapter、ambient capability、配置默认值、Broker observation 或任何旁路都不能在 TASK-048 中完成历史绑定；未来历史绑定只属于独立 reviewed repair contract/task。
- [ ] Migration 必须 expand-only、可重复执行、失败安全，并支持旧 reader/new writer 与 new reader/old rows 的受控兼容阶段。
- [ ] Rollback 不得 DROP、DELETE、清空或覆盖已写入的新 registration broker 绑定、Journal、Snapshot 或恢复证据。
- [ ] registration 未绑定或绑定不完整时，submit/cancel 必须 fail-closed，且不得进入 Broker dispatch；不得从当前 adapter capability 旁路补值。
- [ ] 单元、persistence contract、PostgreSQL integration 与 migration tests 提供 DTO、payload、读写、历史行、Journal/Snapshot/Recovery、幂等 migration、rollout 和 rollback 验收证据。

## Review focus

- 历史数据是否始终 unbound/fail-closed，且不存在静默默认值、当前 capability 回填或 Broker dispatch 旁路。
- registration projection、Journal post-state、Snapshot 与 full-Journal rebuild 是否保持相同绑定证据。
- migration 是否仅扩展、可重入、失败安全，并保留所有历史与回滚审计证据。
- TASK-048 是否完全没有 legacy rebinding 方法、状态迁移或写入口，并明确未来历史绑定只能由独立 reviewed repair contract/task 承担。

## Risks and rollback

- 混合版本部署期间，旧数据和旧 writer 可能缺少绑定；门禁必须保持关闭，直到兼容读写和恢复演练证明安全。
- 任何 legacy 数据、Journal/Snapshot 不一致或 migration 部分失败都必须保持 `UNBOUND`/SAFE；对账或人工处理只能记录/分析证据，不得在 TASK-048 中改成 `BOUND`。
- Rollback 只能停止新 writer、恢复上一兼容 reader 并保留新增列、绑定值和审计证据；禁止破坏性降级。

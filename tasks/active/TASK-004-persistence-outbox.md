---
id: TASK-004
title: Implement Order persistence boundary, journal, snapshot, and outbox
status: active
depends_on: [TASK-002, TASK-003, TASK-013]
spec_refs: [INV-CONSISTENCY, REPO-ORDER, STORAGE-SOT, STORAGE-ORDER-PERSISTENCE, STORAGE-OUTBOX, PORTS-ORDER-PERSISTENCE, WF-ORDER-COMMIT, WF-OUTBOX-PUBLICATION, WF-RECOVERY, CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-ORDER-STATUS-V1, CONTRACT-ERROR-CATALOG]
allowed_paths:
  - src/quantiqmt/order/application/persistence/**
  - src/quantiqmt/order/infrastructure/**
  - src/quantiqmt/messaging/outbox/**
  - tests/unit/order/application/**
  - tests/contract/persistence/**
  - tests/integration/persistence/**
  - migrations/**
  - .github/workflows/ci.yml
forbidden_paths: [src/quantiqmt/order/domain/**, src/quantiqmt/broker/**, src/quantiqmt/strategy/**]
verification:
  commands:
    - poetry run pytest tests/unit/order/application tests/contract/persistence tests/integration/persistence
    - poetry run mypy src/quantiqmt/order/application/persistence src/quantiqmt/order/infrastructure src/quantiqmt/messaging/outbox
---

# Objective

实现 Application persistence DTO/Port、PostgreSQL Order Repository、Append-only Journal、Snapshot 恢复和事务 Outbox，并在真实 PostgreSQL CI 中证明原子性与崩溃恢复。

## Non-goals

- 不修改 Order 状态机或新增业务状态。
- 不实现 Broker、Redis Event Backbone、Inbox consumer 或 Strategy。
- 不在数据库事务内调用外部服务。

## Deliverables

- Application 层不可变 persistence DTO、Repository/Clock/ClientOrderIdFactory 边界。
- `OrderRegistrationDraft`、`OrderSnapshot`、`ClaimPolicy`、`ClaimedMessage`、`PublishFailure`、`OutboxMutationResult`、`SnapshotLookup`、`RecoveryPage` 等 Port DTO。
- Expand-only PostgreSQL migration、约束和索引。
- Repository 注册幂等、CAS save、Snapshot/full Journal recovery。
- Outbox claim/lease/reclaim/publish acknowledgement/renew 与 dead-letter 行为；所有 Store 操作必须有 deadline。
- 全量恢复订单分页枚举、Snapshot 损坏诊断、Journal projection rebuild。
- PostgreSQL service CI、并发/kill-boundary/恢复集成测试。

## Acceptance criteria

- [ ] Order+Journal+Outbox 原子提交，任一写入失败没有部分状态。
- [ ] 相同 intent/fingerprint 幂等返回已有订单；冲突返回 QQ-STORAGE-7001。
- [ ] intent/client order 和 aggregate version 唯一约束有效。
- [ ] 并发保存返回 QQ-COMMON-1003，不覆盖数据。
- [ ] Journal append-only、版本连续且 checksum chain 可验证。
- [ ] Snapshot checksum 损坏时记录 QQ-STORAGE-7003、丢弃该恢复尝试中的 Snapshot 并从完整 Journal 重建；Journal 损坏保持恢复屏障关闭。
- [ ] Outbox Worker 崩溃后可 reclaim；相同 message_id 允许重复发布但不产生新业务事实。
- [ ] claim token fencing、lease 未过期校验、最大尝试、dead-letter、critical lag 安全动作符合 STORAGE-OUTBOX。
- [ ] 旧 Worker 在 lease 过期后不能 renew、mark_published 或 release_failed，返回 QQ-STORAGE-7004。
- [ ] ClientOrderIdFactory 在 Broker 副作用前生成/校验 ID；唯一约束竞争按 QQ-STORAGE-7006 或 bounded retry 处理。
- [ ] 恢复可通过 list_recovery_order_ids 分页枚举所有订单，并能通过 Journal 安全重建 orders projection。
- [ ] PostgreSQL integration tests 不使用 skip/sleep 掩盖缺少服务或竞态。

## Required evidence

- 全部 verification commands、CI PostgreSQL job、migration upgrade/downgrade 安全说明。
- 并发注册/CAS、order_id/client_order_id 唯一竞争、事务中断、invalid snapshot、journal gap、projection rebuild、publish-before-ack crash、lease-expired ack/renew/release fenced 的测试证据。
- Review 必须确认未修改 `src/quantiqmt/order/domain/**`，未调用 Broker、Redis Event Backbone 或外部网络。

## Risks and rollback

- Migration 只允许 expand；必须提供 downgrade safety 分析，禁止为满足形式要求编写破坏数据的 downgrade。
- 未验证恢复前不得打开新 OrderIntent 屏障。
- Rollback 只允许停止 writers/workers 并保留 PostgreSQL rows；禁止删除 Journal、Snapshot 或 Outbox 审计数据。

---
id: TASK-004
title: Implement Order repository journal and outbox
status: blocked
depends_on: [TASK-002, TASK-003]
spec_refs: [INV-CONSISTENCY, REPO-ORDER, STORAGE-SOT]
allowed_paths: [src/quantiqmt/order/infrastructure/**, src/quantiqmt/messaging/outbox/**, tests/integration/persistence/**, migrations/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/strategy/**]
verification:
  commands: ["poetry run pytest tests/integration/persistence"]
---

# Objective

实现 PostgreSQL Order Journal、Snapshot、乐观锁和事务 Outbox。

## Acceptance criteria

- [ ] Order+Journal+Outbox 原子提交。
- [ ] intent/client order 和 aggregate version 唯一约束有效。
- [ ] 并发保存返回 QQ-COMMON-1003，不覆盖数据。
- [ ] Outbox Worker 崩溃后可 reclaim，允许重复发布。
- [ ] Snapshot checksum 损坏时从 Journal 重建。

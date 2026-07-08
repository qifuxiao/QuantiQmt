---
id: TASK-013
title: Complete Order persistence, journal, snapshot, and outbox contracts
status: active
depends_on: [TASK-003, TASK-012]
spec_refs: [INV-CONSISTENCY, REPO-ORDER, STORAGE-SOT, CONTRACT-CATALOG, WF-RECOVERY]
allowed_paths:
  - spec/manifest.yaml
  - spec/repositories/order-repository.md
  - spec/storage/**
  - spec/contracts/**
  - spec/interfaces/**
  - spec/workflows/**
  - tasks/active/TASK-013-order-persistence-contracts.md
  - tasks/backlog/TASK-004-persistence-outbox.md
  - tasks/index.yaml
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结 Order 持久化身份、Repository、Journal、Snapshot 和事务 Outbox 的实施契约，消除 TASK-004 需要自行发明字段、DTO、恢复语义和并发行为的空间。

## Acceptance criteria

- [ ] 明确 `order_id`、`intent_id`、`client_order_id` 的归属、生成时点、可空性、唯一性和恢复规则。
- [ ] 冻结 Repository Port 的逻辑签名、乐观锁、幂等创建、事务边界和 canonical 错误码。
- [ ] 冻结 Journal entry、Snapshot envelope/checksum、Outbox record/lease/reclaim 的逻辑 Schema。
- [ ] 明确 Order 状态迁移、Journal 事实与现有 public Event/Outbox message 的映射，不私自新增含义。
- [ ] 明确 Snapshot 损坏、Journal 重放、Outbox Worker 崩溃和重复发布的恢复流程。
- [ ] Spec 版本、Catalog/Manifest、兼容性、迁移、部署顺序和回滚说明同步更新。
- [ ] TASK-004 更新依赖和 `spec_refs`，在 TASK-013 评审通过前保持 blocked。
- [ ] 不修改业务代码、测试或数据库 migration。

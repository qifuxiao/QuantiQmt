---
id: TASK-012
title: Complete Order trade and broker report merge semantics
status: active
depends_on: [TASK-002]
spec_refs: [INV-TRADING, INV-CONSISTENCY, SM-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING, CONTRACT-BROKER-TRADE-V1, CONTRACT-BROKER-ORDER-REPORTED-V1]
allowed_paths: [spec/state-machines/order.yaml, spec/workflows/cancel-order.yaml, spec/workflows/trade-accounting.yaml, spec/manifest.yaml, docs/30-Trading/**, tasks/index.yaml, tasks/backlog/TASK-003-order-domain.md]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands: ["poetry run python scripts/validate_specs.py", "poetry run pytest tests/spec"]
---

# Objective

补全 Order 在多笔部分成交、撤单竞态、重复及乱序 Broker/Trade 事实下的规范语义，使 TASK-003 可以无歧义实现。

## Acceptance criteria

- [ ] PARTIALLY_FILLED、CANCEL_PENDING、CANCEL_UNKNOWN 的部分/全部成交迁移完整。
- [ ] Broker report 与 Trade fact identity、幂等 no-op 和乱序归并规则明确。
- [ ] 每个具名 Guard 的输入事实、失败语义和版本约束明确。
- [ ] Aggregate 初始/恢复版本与累计成交不变量明确。
- [ ] UNKNOWN 状态禁止自动重提、重撤，成交事实仍不得忽略。
- [ ] 独立架构 Review APPROVE 后 TASK-003 才能恢复 active。
- [ ] 不产生任何业务代码。

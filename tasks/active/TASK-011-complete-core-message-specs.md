---
id: TASK-011
title: Complete and approve core order risk execution message schemas
status: active
depends_on: [TASK-000]
spec_refs: [CONTRACT-CATALOG, CONTRACT-MESSAGE-ENVELOPE-V1, SM-ORDER, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING]
allowed_paths: [spec/contracts/**, spec/manifest.yaml, docs/10-EventDriven/**, tasks/index.yaml, tasks/backlog/TASK-002-message-contracts.md, tasks/backlog/TASK-003-order-domain.md, tasks/backlog/TASK-005-risk-engine.md, tasks/backlog/TASK-006-broker-simulator.md]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands: ["poetry run python scripts/validate_specs.py", "poetry run pytest tests/spec"]
---

# Objective

在实现消息 DTO 前补齐并评审 Order/Risk/Execution/Broker 的 active JSON Schema，将相关消息从 planned 转为 active。

## Required schemas

- oms.order_registered.v1
- risk.order_evaluated.v1
- broker.order_reported.v1
- execution.attempt_started.v1
- execution.outcome_unknown.v1
- execution.cancel_order.v1
- ledger.trade_posted.v1
- portfolio.position_changed.v1

## Acceptance criteria

- [ ] 每个 Schema 定义字段、精度、枚举、必填项和 additionalProperties。
- [ ] Contract Catalog 的 owner/publisher/consumer/status 与 Schema 一致。
- [ ] valid/minimal/maximal/invalid/unknown-enum fixture 要求明确。
- [ ] Submit/Cancel UNKNOWN、成交去重和 Risk snapshot version 均可表达。
- [ ] 人工架构评审批准后才把消息状态改为 active。
- [ ] 不产生任何业务代码。

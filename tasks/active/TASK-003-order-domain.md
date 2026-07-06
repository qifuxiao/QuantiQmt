---
id: TASK-003
title: Implement OMS order aggregate and state machine
status: active
depends_on: [TASK-001, TASK-002, TASK-012]
spec_refs: [INV-TRADING, INV-CONSISTENCY, SM-ORDER, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-BROKER-TRADE-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1]
allowed_paths: [src/quantiqmt/order/domain/**, tests/unit/order/**, tests/property/order/**]
forbidden_paths: [src/quantiqmt/order/infrastructure/**, src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/order tests/property/order", "poetry run mypy src/quantiqmt/order/domain"]
---

# Objective

实现纯 Domain Order 聚合、状态迁移、Guard、领域事件和不变量。

## Acceptance criteria

- [ ] YAML 中所有合法迁移覆盖，未声明迁移拒绝为 QQ-OMS-5002。
- [ ] cum_quantity 单调且不超过 quantity。
- [ ] UNKNOWN 不产生自动重新提交动作。
- [ ] 重复/乱序输入 Property Test 保持最终不变量。
- [ ] Domain 无 DB、Redis、QMT、系统时间依赖。

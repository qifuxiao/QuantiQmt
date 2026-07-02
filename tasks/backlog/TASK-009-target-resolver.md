---
id: TASK-009
title: Implement deterministic target resolver
status: blocked
depends_on: [TASK-007, TASK-008]
spec_refs: [PORTS-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, INV-RISK]
allowed_paths: [src/quantiqmt/targeting/**, tests/unit/targeting/**, tests/property/targeting/**]
forbidden_paths: [src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/targeting tests/property/targeting"]
---

# Objective

实现 TargetWeight/TargetPosition 到 OrderIntent 的确定性转换。

## Acceptance criteria

- [ ] delta 扣除当前归属持仓和活动订单 expected effect。
- [ ] lot/tick/deadband/price reference 明确且可审计。
- [ ] 相同 target+snapshot 产生相同 resolution/idempotency key。
- [ ] stale price、过期 target 和越权 scope 不产生 Intent。

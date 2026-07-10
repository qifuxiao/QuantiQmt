---
id: TASK-009
title: Implement deterministic target resolver
status: blocked
depends_on: [TASK-007, TASK-008, TASK-019]
spec_refs: [PORTS-STRATEGY, CONTRACT-STRATEGY-TARGET-V1, INV-RISK, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [src/quantiqmt/targeting/**, tests/unit/targeting/**, tests/property/targeting/**]
forbidden_paths: [src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/targeting tests/property/targeting"]
---

# Objective

实现 TargetWeight/TargetPosition 到 OrderIntent 的确定性转换。

## Blocking reason

需要 TASK-019 冻结 InstrumentSpec、price reference、lot/tick rounding、deadband、active order expected effect、target mandate/scope 和 deterministic id/idempotency key 算法。

## Non-goals

- 不做最终 Risk approve。
- 不直接调用 Broker、OMS Repository 或数据库。
- 不处理 Portfolio/Ledger 权威计算，仅读取版本化 Snapshot。

## Acceptance criteria

- [ ] delta 扣除当前归属持仓和活动订单 expected effect。
- [ ] lot/tick/deadband/price reference 明确且可审计。
- [ ] 相同 target+snapshot 产生相同 resolution/idempotency key。
- [ ] stale price、过期 target 和越权 scope 不产生 Intent。
- [ ] Property tests 覆盖 rounding、cash buffer、sell-to-zero、target replay 和 active order overlap。

## Review focus

- Resolver 是否 deterministic。
- 是否把目标转换结果与 Risk 决策混淆。
- 是否保留足够审计字段解释每个 NoAction/Rejected。

## Risks and rollback

- 错误 delta 会造成过买/过卖；无法证明 deterministic 前不得解锁。

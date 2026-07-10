---
id: TASK-005
title: Implement deterministic risk evaluator
status: blocked
depends_on: [TASK-003, TASK-015]
spec_refs: [INV-RISK, WF-SUBMIT-ORDER, CONTRACT-ERROR-CATALOG, CONTRACT-RISK-ORDER-EVALUATED-V1, REVIEW-IMPLEMENTATION-READINESS-0.5]
allowed_paths: [src/quantiqmt/risk/**, tests/unit/risk/**, tests/property/risk/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/storage/**]
verification:
  commands: ["poetry run pytest tests/unit/risk tests/property/risk", "poetry run mypy src/quantiqmt/risk"]
---

# Objective

实现基于不可变快照和版本化规则集的纯 RiskEvaluator。

## Blocking reason

TASK-005 不得实现，直到 TASK-015 补齐 RiskInput、Snapshot DTO、RuleSet、规则排序、硬限额、fail-closed taxonomy、减仓例外和审计输出契约。

## Non-goals

- 不访问数据库、Redis、Broker、网络或系统时钟。
- 不推进 Order 状态，不直接调用 OMS Repository。
- 不定义新的 Risk DTO 或规则 DSL；这些必须来自 TASK-015。

## Acceptance criteria

- [ ] 覆盖系统、账户、组合、策略、标的规则层级。
- [ ] stale/partial/timeout fail-closed。
- [ ] 相同输入和版本得到相同 Decision。
- [ ] 输出逐规则测量值、限额、原因和耗时。
- [ ] 无网络、数据库、Broker、系统时间调用。
- [ ] Property tests 覆盖规则顺序、最严格限制优先、减仓例外和 stale snapshot fail-closed。

## Review focus

- Risk 是否纯计算。
- RuleSet 和输入快照是否不可变且版本化。
- 是否所有扩大风险路径都 fail-closed。
- 是否误把 side/position_effect 当作减仓例外。

## Risks and rollback

- Risk reject 默认安全，误放行是 P0。
- 若规则契约不完整，必须停止并回到 spec-change task。

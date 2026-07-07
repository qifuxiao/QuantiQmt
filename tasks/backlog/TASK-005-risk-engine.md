---
id: TASK-005
title: Implement deterministic risk evaluator
status: ready
depends_on: [TASK-003]
spec_refs: [INV-RISK, WF-SUBMIT-ORDER, CONTRACT-ERROR-CATALOG, CONTRACT-RISK-ORDER-EVALUATED-V1]
allowed_paths: [src/quantiqmt/risk/**, tests/unit/risk/**, tests/property/risk/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/storage/**]
verification:
  commands: ["poetry run pytest tests/unit/risk tests/property/risk", "poetry run mypy src/quantiqmt/risk"]
---

# Objective

实现基于不可变快照和版本化规则集的纯 RiskEvaluator。

## Acceptance criteria

- [ ] 覆盖系统、账户、组合、策略、标的规则层级。
- [ ] stale/partial/timeout fail-closed。
- [ ] 相同输入和版本得到相同 Decision。
- [ ] 输出逐规则测量值、限额、原因和耗时。
- [ ] 无网络、数据库、Broker、系统时间调用。

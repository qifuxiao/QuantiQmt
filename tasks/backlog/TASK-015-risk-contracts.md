---
id: TASK-015
title: Complete Risk engine L4 contracts
status: ready
depends_on: [TASK-014]
spec_refs: [INV-RISK, INV-CONSISTENCY, WF-SUBMIT-ORDER, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-ERROR-CATALOG, NFR-PERFORMANCE, NFR-OBSERVABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tasks/backlog/TASK-005-risk-engine.md, tasks/backlog/TASK-015-risk-contracts.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
---

# Objective

冻结 RiskInput、Snapshot、RuleSet、逐规则结果、fail-closed taxonomy 和 RiskDecision 审计契约，使 TASK-005 可以无歧义实现纯 RiskEvaluator。

## Non-goals

- 不实现 Risk 代码。
- 不修改 Order 状态机。
- 不放宽任何 Risk 不变量。

## Acceptance criteria

- [ ] 定义 RiskInput DTO：Order snapshot、account snapshot、portfolio snapshot、market snapshot、rule_set_version 和 input_version。
- [ ] 定义 Snapshot freshness/partial/stale/timeout 语义与 canonical error/reject reason。
- [ ] 定义 RuleSet schema：系统硬限额、账户/组合/策略/标的规则、优先级、最严格结果优先。
- [ ] 定义 reduce-only/平仓例外，禁止通过 side 字段猜测减仓。
- [ ] 定义 RiskDecision 与 RiskRuleResult 字段、审计事件映射和延迟测量方式。
- [ ] 更新 TASK-005，使其可直接实现并验证。

## Review focus

- 是否所有扩大风险路径 fail-closed。
- 是否 Risk 保持纯计算，不访问 I/O 或系统时间。
- 是否规则结果足以复盘一次订单的通过/拒绝原因。

## Risks and rollback

- 错误放行是 P0；规范不完整时不得恢复 TASK-005。

---
id: TASK-015
title: Complete Risk engine L4 contracts
status: active
depends_on: [TASK-014]
spec_refs: [INV-RISK, INV-CONSISTENCY, WF-SUBMIT-ORDER, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-ERROR-CATALOG, NFR-PERFORMANCE, NFR-OBSERVABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tasks/active/README.md, tasks/active/TASK-015-risk-contracts.md, tasks/backlog/TASK-005-risk-engine.md, tasks/index.yaml]
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

- [x] 定义 RiskInput DTO：Order snapshot、account snapshot、portfolio snapshot、market snapshot、rule_set_version 和 input_version。
- [x] 定义 Snapshot freshness/partial/stale/timeout 语义与 canonical error/reject reason。
- [x] 定义 RuleSet schema：系统硬限额、账户/组合/策略/标的规则、优先级、最严格结果优先。
- [x] 定义 reduce-only/平仓例外，禁止通过 side 字段猜测减仓。
- [x] 定义 RiskDecision 与 RiskRuleResult 字段、审计事件映射和延迟测量方式。
- [x] 更新 TASK-005，使其可直接实现并验证。

## Evidence

- Spec 0.6.0 新增机器可校验的 RiskInput、RuleSet、RiskDecision、RiskAuditOutput schema，以及 `PORTS-RISK` 纯 evaluator/runner 逻辑签名。
- 固定 synthetic/hard/scoped rule ordering、strict-result aggregation、canonical hash/UUID5、hard-limit policy、Decimal metrics 和完整 QQ-RISK fail-closed taxonomy。
- reduce-only 仅允许版本匹配、数量不超、signed projection 绝对仓位下降且不翻仓的显式 evidence；hard/validity/timeout/trading/instrument guards 不可豁免。
- `risk.order_evaluated.v1` 公共 schema 保持不变；PORTS-RISK 定义从完整 internal audit output 到现有权威审计事件的严格兼容投影。
- TASK-005 已引用全部冻结契约并具备实现级 deliverables、property-test matrix 与独立 Review activation gate。
- `poetry run python scripts/validate_specs.py`: passed。
- `poetry run pytest tests/spec tests/contract`: passed，143 tests。
- RiskAuditOutput → RiskDecision URN cross-schema reference: resolved。
- 未修改 `src/**`、`tests/**`、`migrations/**`；TASK-015 保持 active，等待独立 Review。

## Review focus

- 是否所有扩大风险路径 fail-closed。
- 是否 Risk 保持纯计算，不访问 I/O 或系统时间。
- 是否规则结果足以复盘一次订单的通过/拒绝原因。

## Risks and rollback

- 错误放行是 P0；规范不完整时不得恢复 TASK-005。

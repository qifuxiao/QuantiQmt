---
id: TASK-005
title: Implement deterministic risk evaluator
status: active
depends_on: [TASK-003, TASK-015]
spec_refs: [INV-RISK, INV-CONSISTENCY, WF-SUBMIT-ORDER, CONTRACT-RISK-INPUT-V1, CONTRACT-RISK-RULE-SET-V1, CONTRACT-RISK-DECISION-V1, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, CONTRACT-ERROR-CATALOG, PORTS-RISK, NFR-PERFORMANCE, NFR-OBSERVABILITY]
allowed_paths: [src/quantiqmt/risk/**, tests/unit/risk/**, tests/property/risk/**]
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/storage/**]
verification:
  commands: ["poetry run pytest tests/unit/risk tests/property/risk", "poetry run mypy src/quantiqmt/risk"]
---

# Objective

实现基于不可变快照和版本化规则集的纯 RiskEvaluator。

## Activation gate

TASK-015 已在 Spec 0.6 冻结 RiskInput、Snapshot DTO、RuleSet、规则排序、硬限额、fail-closed taxonomy、减仓例外、RiskDecision 和审计输出契约，并已通过独立 Review、合并 PR #24、由人类授权标记 completed。TASK-005 已由人类明确分配并激活，可以严格依照既有契约实施；不得重新发明 Risk DTO、规则 DSL、错误码或计时语义。

## Non-goals

- 不访问数据库、Redis、Broker、网络或系统时钟。
- 不推进 Order 状态，不直接调用 OMS Repository。
- 不定义新的 Risk DTO 或规则 DSL；这些必须来自 TASK-015。

## Deliverables

- `CONTRACT-RISK-INPUT-V1`、`CONTRACT-RISK-RULE-SET-V1`、`CONTRACT-RISK-DECISION-V1`、`CONTRACT-RISK-AUDIT-OUTPUT-V1` 的不可变 typed DTO 与 schema validation。
- `PORTS-RISK` 定义的纯 `RiskEvaluator`、确定性 rule ordering、hard-limit validation、strict-result aggregation 和 reduce-only evidence validation。
- 外层 `RiskEvaluationRunner` 的 monotonic per-rule/total latency、timeout guard、完整 internal audit output、权威 `risk.order_evaluated.v2` 与 `risk.order_evaluated.v1` 兼容投影；Runner 与纯 evaluator 必须可独立测试。
- `PORTS-RISK.RiskAuditSemanticValidator`，在 v1 projection、v1/v2 Outbox 与 Execution 前强制校验 result/timing identity、连续顺序、唯一性、count、latency sum 和唯一 timeout guard 语义；失败不得修补或发布并 fail-closed。
- canonical JSON/SHA-256、deterministic UUID5 decision identity、semantic decision hash。

## Acceptance criteria

- [ ] 精确实现 PORTS-RISK 的 phase/scope/priority/rule_id 排序，覆盖系统、账户、组合、策略、标的层级；priority 不改变 REJECT 优先语义。
- [ ] stale/partial/snapshot-timeout/unavailable/snapshot-version-mismatch/rule-set-version-mismatch/input-invalid/rule-set-invalid/evaluation-timeout 全部映射 canonical QQ-RISK code 并 fail-closed。
- [ ] 相同 RiskInput 和 RuleSet 得到逐字节相同的语义 Decision、UUID5 decision_id 和 hash；任何 latency/evaluated_at 不进入语义 hash。
- [ ] 所有 SYSTEM.HARD 规则不可删除、不可被动态配置放宽、不可被 reduce-only 例外绕过。
- [ ] reduce-only 仅接受版本匹配、数量不超、绝对仓位下降且不翻仓的显式 evidence；side/CLOSE/AUTO 均不构成证据。
- [ ] 输出所有逐规则 evaluation_index、phase、scope、metric、typed 测量值、typed 限额、原因、例外标记；Runner 额外输出独立 monotonic RuleTiming、完整 internal audit output、权威 v2 与严格的 v1 lossy compatibility projection。
- [ ] RiskAuditSemanticValidator 拒绝 missing/duplicate/extra/unsorted/mismatched timing、非连续 index、错误 completed count、latency sum 不一致和非末尾/多重 timeout guard；v1 projection 只接受 validator 已通过的 v2 audit。
- [ ] V1 仅支持 RiskInput/RuleSet/account/portfolio/market 单一 ISO valuation currency；金额动态 limit currency 必须匹配，跨币种/FX 输入 fail-closed。
- [ ] evaluator 无网络、数据库、Broker、Redis、环境变量、可变全局状态或任何时钟调用；Runner 只通过注入 Clock Port 计时。
- [ ] Property tests 覆盖排列稳定性、同 metric 多规则最严格结果、hard cap 不可放宽、每个 fail-closed taxonomy、reduce evidence 边界、Decimal/float 拒绝、timeout late-PASS 不可覆盖。

## Review focus

- Risk 是否纯计算。
- RuleSet 和输入快照是否不可变且版本化。
- 是否所有扩大风险路径都 fail-closed。
- 是否误把 side/position_effect 当作减仓例外。
- 是否把 audit latency 混入确定性 Decision，或让 timeout 后的 late PASS 覆盖 REJECT。
- 是否存在动态规则绕过 SYSTEM.HARD、缺失 metric 默认 0、float 比较或规则短路导致审计不完整。

## Risks and rollback

- Risk reject 默认安全，误放行是 P0。
- 若规则契约不完整，必须停止并回到 spec-change task。

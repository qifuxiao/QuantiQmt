---
id: TASK-015
title: Complete Risk engine L4 contracts
status: completed
depends_on: [TASK-014]
spec_refs: [INV-RISK, INV-CONSISTENCY, WF-SUBMIT-ORDER, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, CONTRACT-ERROR-CATALOG, NFR-PERFORMANCE, NFR-OBSERVABILITY]
allowed_paths:
  - spec/manifest.yaml
  - spec/contracts/**
  - spec/interfaces/**
  - spec/workflows/**
  - spec/nfr/**
  - tests/contract/messages/**
  - tasks/active/README.md
  - tasks/active/TASK-015-risk-contracts.md
  - tasks/backlog/TASK-005-risk-engine.md
  - tasks/index.yaml

forbidden_paths:
  - src/**
  - migrations/**
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: unverified
  review_status: reported_unverified
  release_status: prohibited
  remediation_task: TASK-031
  completion_evidence: {mode: historical_evidence_unverifiable, change_pr: unverifiable, reviewed_head_sha: unverifiable, review_verdict: reported_unverified, reviewer: unverifiable, evidence_url: unverifiable, merge_commit_sha: unverifiable, human_authorization_evidence: TASK-031 governance recovery authorization}
---

### Governance delivery evidence

Historical Review/CI/merge evidence is not independently verifiable; no approval is inferred.

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

- 人类项目成员明确授权本任务将 `tests/contract/messages/**` 加入 `allowed_paths`，并仅移除与该精确授权冲突的 `tests/**` forbidden 条目；该授权只覆盖 Risk 契约 Schema 的 golden fixtures、生成器和消息契约验证。其他 `tests/**` 目录仍未授权，`src/**`、`migrations/**` 继续禁止，且不得用于业务代码、其他测试或范围外重构。
- Spec 0.6.0 新增机器可校验的 RiskInput、RuleSet、RiskDecision、RiskAuditOutput schema，以及 `PORTS-RISK` 纯 evaluator/runner 逻辑签名。
- 固定 synthetic/hard/scoped rule ordering、strict-result aggregation、canonical hash/UUID5、hard-limit policy、Decimal metrics 和完整 QQ-RISK fail-closed taxonomy。
- reduce-only 仅允许版本匹配、数量不超、signed projection 绝对仓位下降且不翻仓的显式 evidence；hard/validity/timeout/trading/instrument guards 不可豁免。
- `risk.order_evaluated.v1` 公共 schema 保持不变并作为 lossy compatibility projection；新增 `risk.order_evaluated.v2` 以完整 RiskAuditOutput 作为 typed 权威审计事件。
- V1 冻结单一 ISO `valuation_currency`，所有金额 hard/dynamic limit 与 Input/RuleSet/account/portfolio/market 精确匹配，跨币种/FX fail-closed。
- RiskRuleResult 以 DECIMAL/INTEGER/BOOLEAN/STRING/STRING_SET 判别值保留逐规则 measured/limit；latency 仅位于与结果一对一 join 的 RuleTiming。
- TASK-005 已引用全部冻结契约并具备实现级 deliverables、property-test matrix 与独立 Review activation gate。
- bundled Poetry `run python scripts/validate_specs.py`: passed；裸 `poetry` 不在 PATH。
- bundled Poetry `run pytest tests/spec tests/contract`: passed，159 tests。
- self-contained RiskOrderEvaluatedV2 是 RiskAuditOutput/RiskDecision 的唯一机器源；两个内部契约的 Draft 2020-12 URN/JSON Pointer 引用已做 runtime resolution validation。
- v2 BOOLEAN 与 STRING/STRING_SET typed values 通过 runtime/official validator；旧 decimal-string boolean 编码被拒绝；v1 version-aware golden fixtures 保持通过。
- Review P1 修复冻结 `RiskAuditSemanticValidator`：标准 Schema 负责结构，validator 强制 result/timing 连续顺序、唯一性、一一 identity/count、latency sum 和唯一 timeout guard；任何失败在 v1 projection、Outbox 或 Execution 前 fail-closed 且不得修补。
- Review P1 验证：`poetry run python scripts/validate_specs.py` passed；`poetry run pytest tests/spec tests/contract` 192 passed；Review 的 timing rule_id、evaluation_index、completed count 三个 schema-valid 复现均被 semantic validator 拒绝。
- 未修改 `src/**`、`migrations/**`；TASK-015 在 PR #24 合并并获得人类状态迁移授权前保持 active。
- 独立 Review 已对 PR #24 的 approved head `e8c3aa4454f001f2d1d53ee9ad448979b8475b2b` 给出 APPROVE，且无 P0-P3 finding；PR #24 已合并为 `26640e109a5d7808b8bddfcfb9b0379c4df05883`。
- 人类项目成员明确授权本次任务治理操作将 TASK-015 从 active 移入 completed，并据此写入本 completed 状态；该授权不激活 TASK-005，也不授权任何业务实现。

## Review focus

- 是否所有扩大风险路径 fail-closed。
- 是否 Risk 保持纯计算，不访问 I/O 或系统时间。
- 是否规则结果足以复盘一次订单的通过/拒绝原因。

## Risks and rollback

- 错误放行是 P0；规范不完整时不得恢复 TASK-005。

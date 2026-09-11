---
id: TASK-005
title: Implement deterministic risk evaluator
status: blocked
depends_on: [TASK-003, TASK-015, TASK-029]
spec_refs: [INV-RISK, INV-CONSISTENCY, WF-SUBMIT-ORDER, CONTRACT-RISK-INPUT-V1, CONTRACT-RISK-RULE-SET-V1, CONTRACT-RISK-DECISION-V1, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, CONTRACT-ERROR-CATALOG, PORTS-RISK, NFR-PERFORMANCE, NFR-OBSERVABILITY]
allowed_paths:
  - src/quantiqmt/risk/**
  - tests/unit/risk/**
  - tests/property/risk/**
  - ai/packets/TASK-005-IMPLEMENTATION-v1.md
  - ai/handoffs/TASK-005-IMPLEMENTATION-v1.yaml
  - tasks/active/TASK-005-risk-engine.md
  - scripts/validate_agent_environment.py
  - tests/spec/test_validate_agent_environment.py
forbidden_paths: [src/quantiqmt/broker/**, src/quantiqmt/storage/**]
verification:
  commands: ["poetry run pytest tests/unit/risk tests/property/risk", "poetry run mypy src/quantiqmt/risk"]
  required_lanes:
    - lane: portable
      capability: portable
      minimum_records: 1
      commands:
        - poetry run pytest tests/unit/risk tests/property/risk
        - poetry run mypy src/quantiqmt/risk
  prohibited_lanes:
    - windows_miniqmt
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: not_started
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

实现基于不可变快照和版本化规则集的纯 RiskEvaluator。

## Suspension gate — 2026-09-11

本次 Human 授权暂停 TASK-005，并单独激活 TASK-058 规范变更任务。
PR #117 已关闭、未合并；它不是 accepted completion。
停止 Head：`88d217661f6d6c127758fc245336a9f806788ab9`。

- Supersession authority: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5628617915
- Canonical STOP: https://github.com/qifuxiao/QuantiQmt/pull/117#issuecomment-5629435266
- Preserved implementation: https://github.com/qifuxiao/QuantiQmt/pull/117

旧分支、commit、Packet/Handoff、Review 和环境 evidence 保留，不改写、不重用为
新 Head 的权威。下列 activation/Plan-v1/实施准备段落仅保留历史上下文，
不能覆盖本暂停门禁。delivery 字段描述 main 中未合并本轮实现的状态，
不表示 PR #117 从未开展工作，也不把关闭当作完成。

恢复必须等待 TASK-058 规范变更独立评审、人类合并及可信完成后，由 Human 另行
授权 TASK-005 重规划和激活；现有依赖列表保留，恢复时再冻结新规范依赖。
新 Implementation PR 必须从届时核验的 exact main 建立新 Base、Packet、
assignment 和 Handoff，不沿用 PR #117 的冻结 Base。不得在本次准备中修复 Risk。

## Activation gate

本次 Human 授权仅激活 TASK-005。TASK-003、TASK-015、TASK-029 均为可信
completed，正式 delivery_is_unlockable 检查通过；历史“已分配”文字不构成本轮
Implementation assignment。本 activation-only PR 不开始实现或创建 Packet/Handoff。
实现前仍须满足现有 assignment、single-writer 和 Handoff 门禁。

- Plan version: `TASK-005-PLAN-v1`
- Planning Base: `f09811a17972d1d446a95806821fd80586858e11`
- TASK-003 evidence: https://github.com/qifuxiao/QuantiQmt/pull/113#pullrequestreview-5139314381
- TASK-003 evidence record merge: https://github.com/qifuxiao/QuantiQmt/pull/114
- TASK-015 evidence: https://github.com/qifuxiao/QuantiQmt/pull/27#pullrequestreview-4709936693
- TASK-029 evidence: https://github.com/qifuxiao/QuantiQmt/pull/110#pullrequestreview-5133890761

目标演示：使用固定不可变 RiskInput/RuleSet 得到可重复的 Decision、decision_id
与 hash，并对非法快照、硬限额和 timeout 确定性拒绝。复用 TASK-029 已接受的
Schema → semantic validation → freeze 边界，不重复发明 DTO 或规则 DSL。
本阶段不访问 Mini QMT、账户、行情或交易接口，不授权 release 或其他任务激活。

## Non-goals

本轮实施准备修订仅允许补齐上述精确路径、lanes 及 TASK-005 environment
validator 支持；不授权业务实现、发布 evidence 或创建真实 Packet/Handoff。
后续 Handoff 使用标准拓扑：从准备修订合并后的同一 exact main Base 创建
packet-only PR 和独立 add-only Handoff commit，Human assignment 绑定 packet-only
Starting Head；Implementation Agent 首次以无改写 merge 同步 Handoff。
沿用现有 schema 的 `repair_context.superseded_head_sha` 字段绑定该 Starting Head，
这只是既有字段名，不表示存在虚构的历史 Repair PR。task blob 在 Base/Head 保持
一致，Packet identity 与 Handoff filename stem 均为 `TASK-005-IMPLEMENTATION-v1`。
业务 Implementation Handoff 不应授予 task、validator 或 spec-test 写权限；
这三条准备路径仅限本次 Human 授权，不得被后续实现自动继承。

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

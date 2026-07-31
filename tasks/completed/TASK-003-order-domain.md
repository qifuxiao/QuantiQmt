---
id: TASK-003
title: Implement OMS order aggregate and state machine
status: completed
depends_on: [TASK-001, TASK-002, TASK-012]
spec_refs: [INV-TRADING, INV-CONSISTENCY, SM-ORDER, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING, CONTRACT-ORDER-REGISTERED-V1, CONTRACT-RISK-ORDER-EVALUATED-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-BROKER-TRADE-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1]
allowed_paths: [src/quantiqmt/order/domain/**, tests/unit/order/**, tests/property/order/**]
forbidden_paths: [src/quantiqmt/order/infrastructure/**, src/quantiqmt/broker/**]
verification:
  commands: ["poetry run pytest tests/unit/order tests/property/order", "poetry run mypy src/quantiqmt/order/domain"]
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

# Objective

实现纯 Domain Order 聚合、状态迁移、Guard、领域事件和不变量。

## Acceptance criteria

- [x] YAML 中所有合法迁移覆盖，未声明迁移拒绝为 QQ-OMS-5002。
- [x] cum_quantity 单调且不超过 quantity。
- [x] UNKNOWN 不产生自动重新提交动作。
- [x] 重复/乱序输入 Property Test 保持最终不变量。
- [x] Domain 无 DB、Redis、QMT、系统时间依赖。

## Evidence

- Python transition catalog 与 `SM-ORDER` 的 80 条迁移完全一致。
- Structured Guard、Broker/Trade fact identity、冲突 fingerprint、stale report 和恢复一致性均已实现。
- 多笔部分成交、撤单竞态、UNKNOWN 对账、终态迟到成交及重复/乱序重放均有单元或 Property Test 覆盖。
- `poetry run pytest tests/unit/order tests/property/order`: passed, 29 tests（独立 Review 复验）。
- Full repository pytest: passed, 242 tests（合并前实现门禁）。
- Mypy、Ruff、Spec validation: passed.
- 两个独立 Review 会话均为 `APPROVE`，无未关闭 P0-P3 findings。
- 业务实现由 PR #11 合入 `main`，merge commit `776b010`，日期 2026-07-07。

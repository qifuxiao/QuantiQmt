---
id: TASK-012
title: Complete Order trade and broker report merge semantics
status: completed
depends_on: [TASK-002]
spec_refs: [INV-TRADING, INV-CONSISTENCY, SM-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING, CONTRACT-BROKER-TRADE-V1, CONTRACT-BROKER-ORDER-REPORTED-V1]
allowed_paths: [spec/state-machines/order.yaml, spec/workflows/cancel-order.yaml, spec/workflows/trade-accounting.yaml, spec/manifest.yaml, docs/30-Trading/**, tasks/index.yaml, tasks/backlog/TASK-003-order-domain.md]
forbidden_paths: [src/**, tests/**, migrations/**]
verification:
  commands: ["poetry run python scripts/validate_specs.py", "poetry run pytest tests/spec"]
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

补全 Order 在多笔部分成交、撤单竞态、重复及乱序 Broker/Trade 事实下的规范语义，使 TASK-003 可以无歧义实现。

## Acceptance criteria

- [x] PARTIALLY_FILLED、CANCEL_PENDING、CANCEL_UNKNOWN 的部分/全部成交迁移完整。
- [x] Broker report 与 Trade fact identity、幂等 no-op 和乱序归并规则明确。
- [x] 每个具名 Guard 的输入事实、失败语义和版本约束明确。
- [x] Aggregate 初始/恢复版本与累计成交不变量明确。
- [x] UNKNOWN 状态禁止自动重提、重撤，成交事实仍不得忽略。
- [x] 独立架构 Review APPROVE 后 TASK-003 才能恢复 active。
- [x] 不产生任何业务代码。

## Evidence

- Spec 0.3.0 defines complete multi-fill, cancel-race, terminal correction and UNKNOWN reconciliation paths.
- Fact identity, canonical fingerprints, duplicate no-op, conflict suspension and trade-derived cumulative calculation are normative.
- Named Guard inputs, failure outcomes, atomic no-mutation behavior and recovery state are explicit.
- Compatibility, migration and rollback procedures are documented.
- Independent architecture Review result: `APPROVE`; no P0-P3 findings after correction rounds.
- `poetry run python scripts/validate_specs.py`: passed.
- `poetry run pytest tests/spec`: passed, 4 tests.
- Ruff and Mypy: passed.
- No business code, tests or migrations were changed.
- Merged to `main` as PR #13 (`1c51220`) on 2026-07-06.

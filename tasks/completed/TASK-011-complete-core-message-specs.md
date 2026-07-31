---
id: TASK-011
title: Complete and approve core order risk execution message schemas
status: completed
depends_on: [TASK-000]
spec_refs: [CONTRACT-CATALOG, CONTRACT-MESSAGE-ENVELOPE-V1, SM-ORDER, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, WF-TRADE-ACCOUNTING]
allowed_paths: [spec/contracts/**, spec/manifest.yaml, docs/10-EventDriven/**, tasks/index.yaml, tasks/backlog/TASK-002-message-contracts.md, tasks/backlog/TASK-003-order-domain.md, tasks/backlog/TASK-005-risk-engine.md, tasks/backlog/TASK-006-broker-simulator.md]
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

在实现消息 DTO 前补齐并评审 Order/Risk/Execution/Broker 的 active JSON Schema，将相关消息从 planned 转为 active。

## Required schemas

- oms.order_registered.v1
- risk.order_evaluated.v1
- broker.order_reported.v1
- execution.attempt_started.v1
- execution.outcome_unknown.v1
- execution.cancel_order.v1
- ledger.trade_posted.v1
- portfolio.position_changed.v1

## Acceptance criteria

- [x] 每个 Schema 定义字段、精度、枚举、必填项和 additionalProperties。
- [x] Contract Catalog 的 owner/publisher/consumer/status 与 Schema 一致。
- [x] valid/minimal/maximal/invalid/unknown-enum fixture 要求明确。
- [x] Submit/Cancel UNKNOWN、成交去重和 Risk snapshot version 均可表达。
- [x] 人工架构评审批准后才把消息状态改为 active。
- [x] 不产生任何业务代码。

## Evidence

- Eight required JSON Schemas are registered in Spec 0.2.0 / Contract Catalog 2 and have status `active`.
- Price is strictly positive; Decimal precision is bounded to 18 integer and 8 fractional digits.
- Business datetimes require UTC `Z`; 16 internal ID fields require canonical lowercase UUID strings.
- Submit/Cancel UNKNOWN preserves operation, attempt, fencing and reconciliation evidence without authorizing blind retry.
- Broker trade deduplication tuple and mandatory account/portfolio/market risk snapshot versions are expressible.
- Golden fixture categories and conditional invalid fixtures are frozen in `Message-Contracts.md`.
- Independent architecture Review result: `APPROVE`; no P0-P3 findings after two correction rounds.
- `poetry run python scripts/validate_specs.py`: passed.
- `poetry run pytest`: passed, 74 tests.
- `poetry run ruff check .`: passed.
- `poetry run ruff format --check .`: passed.
- `poetry run mypy src tests`: passed.
- No business code, tests, migrations, unverified criteria, known risks, or spec deviations.
- Merged to `main` as PR #5 (`4982f39`) on 2026-07-02.

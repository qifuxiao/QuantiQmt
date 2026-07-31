---
id: TASK-013
title: Complete Order persistence, journal, snapshot, and outbox contracts
status: completed
depends_on: [TASK-003, TASK-012]
spec_refs: [INV-CONSISTENCY, REPO-ORDER, STORAGE-SOT, CONTRACT-CATALOG, WF-RECOVERY]
allowed_paths:
  - spec/manifest.yaml
  - spec/repositories/order-repository.md
  - spec/storage/**
  - spec/contracts/**
  - spec/interfaces/**
  - spec/workflows/**
  - tasks/completed/TASK-013-order-persistence-contracts.md
  - tasks/backlog/TASK-004-persistence-outbox.md
  - tasks/index.yaml
forbidden_paths: [src/**, tests/**, migrations/**]
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

# Objective

冻结 Order 持久化身份、Repository、Journal、Snapshot 和事务 Outbox 的实施契约，消除 TASK-004 需要自行发明字段、DTO、恢复语义和并发行为的空间。

## Acceptance criteria

- [x] 明确 `order_id`、`intent_id`、`client_order_id` 的归属、生成时点、可空性、唯一性和恢复规则。
- [x] 冻结 Repository Port 的逻辑签名、乐观锁、幂等创建、事务边界和 canonical 错误码。
- [x] 冻结 Journal entry、Snapshot envelope/checksum、Outbox record/lease/reclaim 的逻辑 Schema。
- [x] 明确 Order 状态迁移、Journal 事实与现有 public Event/Outbox message 的映射，不私自新增含义。
- [x] 明确 Snapshot 损坏、Journal 重放、Outbox Worker 崩溃和重复发布的恢复流程。
- [x] Spec 版本、Catalog/Manifest、兼容性、迁移、部署顺序和回滚说明同步更新。
- [x] TASK-004 更新依赖和 `spec_refs`，在 TASK-013 评审通过前保持 blocked。
- [x] 不修改业务代码、测试或数据库 migration。

## Evidence

- Spec 0.4.0 defines Order persistence identity ownership, registration idempotency, Repository Port, Journal, Snapshot, transactional Outbox and recovery contracts.
- `ClientOrderIdFactory` uses `OrderRegistrationDraft`; `OrderSnapshot`, Outbox claim DTOs, lease fencing and deterministic public Event envelope mappings are normative.
- Journal checksum genesis encoding, Snapshot corruption fallback, full startup recovery enumeration and projection rebuild are specified.
- TASK-004 was updated to depend on TASK-013 and remains `blocked` pending follow-up implementation readiness review.
- Independent Review result: `APPROVE`; no P0-P3 findings after correction rounds.
- `poetry run python scripts/validate_specs.py`: passed.
- `poetry run pytest tests/spec tests/contract`: passed, 143 tests.
- Ruff and Mypy: passed.
- No business code, tests or migrations were changed.
- Merged to `main` as PR #18 (`c315335`) on 2026-07-09.

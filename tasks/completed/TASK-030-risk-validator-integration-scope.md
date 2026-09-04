---
id: TASK-030
title: Authorize unified Risk SchemaValidator integration scope
status: completed
depends_on: [TASK-015]
spec_refs: [CONTRACT-RISK-DECISION-V1, CONTRACT-RISK-AUDIT-OUTPUT-V1, CONTRACT-RISK-ORDER-EVALUATED-V2, PORTS-RISK, CONTRACT-CATALOG]
allowed_paths:
  - tasks/active/TASK-029-risk-runtime-schema-contract.md
  - tasks/backlog/TASK-029-risk-runtime-schema-contract.md
  - tasks/backlog/TASK-030-risk-validator-integration-scope.md
  - tasks/active/README.md
  - tasks/index.yaml
forbidden_paths: [src/**, tests/**, spec/**, migrations/**, docs/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: accepted
  implementation_status: merged
  acceptance_status: passed
  review_status: approved
  release_status: prohibited
  completion_evidence:
    mode: present_day_retrospective_revalidation_with_human_accepted_historical_exceptions
    change_pr: https://github.com/qifuxiao/QuantiQmt/pull/44
    reviewed_head_sha: e7c087fc1292f1c57d8352112802ed60f99e9466
    review_verdict: APPROVE
    reviewer: qfxyyy
    evidence_url: https://github.com/qifuxiao/QuantiQmt/pull/44#issuecomment-5537520348
    merge_commit_sha: 238b0ac2c3c82de88c59a900feca8cbb71d38863
    scope_change_pr: https://github.com/qifuxiao/QuantiQmt/pull/42
    scope_reviewed_head_sha: c9b2ce5895a7ffce109ee3e391fc633304415f0f
    scope_merge_commit_sha: 03cdc5b816e1b5ec7c40a63929ed35f486abe9dd
    retrospective_review_created_at: '2026-09-04T07:59:47Z'
    retrospective_review_body_sha256: df3e5858b7b28e7598279a484d4bec18bcb9130280d78010602ad67709096e54
    historical_exceptions: >-
      PR #44 performed ready-to-completed rather than active-to-completed, and
      the completed TASK-030 destination path was absent from the historical
      allowed_paths. Neither PR #42 nor PR #44 had a historical GitHub Review.
      These facts remain disclosed and were accepted only as TASK-030
      retrospective non-product governance exceptions by Human comment
      5537337617; this record does not claim historical pre-merge Approval.
    human_authorization_evidence: >-
      Retrospective authorization comment 5536869310 by qifuxiao, prior
      REQUEST_CHANGES comment 5537295515, and historical exception resolution
      comment 5537337617 by qifuxiao. The final present-day independent
      retrospective APPROVE is comment 5537520348 by qfxyyy.
---

# Objective

为 TASK-029 补齐正式的 Risk 生产路径集成授权，解除统一 Schema → semantic validation → freeze 路径的范围阻断。

## Required scope decision

- 将 `src/quantiqmt/risk/model.py`、`audit.py`、`runner.py`、`evaluator.py` 纳入 TASK-029 allowed_paths；
- 将 `tests/unit/risk/**`、`tests/property/risk/**` 纳入 TASK-029 allowed_paths；
- 仅允许接入既有正式 Risk Schema 和 SchemaValidator，不得新增业务 Event、DTO、错误码或 Risk 规则语义；
- 保持 TASK-005 blocked，直到 TASK-029 完成并独立 Review APPROVE；
- 保留 Order、Persistence、Broker、Redis、Migration 和 docs 为 forbidden paths。

## Acceptance criteria

- [x] TASK-029 allowed_paths 包含 Risk DTO/Audit/Runner/Evaluator 及对应 unit/property tests；
- [x] TASK-029 的 forbidden_paths 不再与上述 Risk 路径冲突；
- [x] TASK-029 明确 Schema → semantic → freeze 的统一生产调用路径；
- [x] 不扩大到其他任务；
- [x] 任务依赖无循环，TASK-005 仍为 blocked；
- [x] TASK-030 仅修改任务治理元数据，不修改业务代码或规范实现。

## Risks and rollback

- 若授权会改变已接受业务语义，停止并创建新的 spec-change；
- 回滚时恢复 TASK-029 原 allowed_paths，并保持 TASK-005 blocked；
- TASK-030 APPROVE 后才能重新激活 TASK-029。

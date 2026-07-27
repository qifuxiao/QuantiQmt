---
id: TASK-030
title: Authorize unified Risk SchemaValidator integration scope
status: ready
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

- [ ] TASK-029 allowed_paths 包含 Risk DTO/Audit/Runner/Evaluator 及对应 unit/property tests；
- [ ] TASK-029 的 forbidden_paths 不再与上述 Risk 路径冲突；
- [ ] TASK-029 明确 Schema → semantic → freeze 的统一生产调用路径；
- [ ] 不扩大到其他任务；
- [ ] 任务依赖无循环，TASK-005 仍为 blocked；
- [ ] TASK-030 仅修改任务治理元数据，不修改业务代码或规范实现。

## Risks and rollback

- 若授权会改变已接受业务语义，停止并创建新的 spec-change；
- 回滚时恢复 TASK-029 原 allowed_paths，并保持 TASK-005 blocked；
- TASK-030 APPROVE 后才能重新激活 TASK-029。

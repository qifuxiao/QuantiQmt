---
id: TASK-022
title: Complete Observability, Config, and Control L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [INV-TRADING, INV-CONSISTENCY, INV-RISK, WF-CONFIG-ACTIVATION, NFR-OBSERVABILITY, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/state-machines/**, spec/nfr/**, tests/contract/messages/**, tasks/active/TASK-022-observability-control-contracts.md, tasks/active/README.md, tasks/backlog/TASK-025-control-observability.md, tasks/index.yaml]
forbidden_paths: [src/**, tests/unit/**, tests/property/**, tests/integration/**, migrations/**]
verification:
  commands:
    - poetry run python scripts/validate_specs.py
    - poetry run pytest tests/spec tests/contract
delivery:
  schema_version: 1
  contract_status: draft
  implementation_status: in_progress
  acceptance_status: not_run
  review_status: pending
  release_status: prohibited
---

# Objective

冻结日志、指标、Trace、告警、配置激活、Kill Switch、system mode、leader/fencing 和 recovery barrier 的 L4 契约。

## Non-goals

- 不实现监控或控制面代码。
- 不接 Prometheus/Grafana/Alertmanager。
- 不修改交易状态机以绕过控制。

## Acceptance criteria

- [ ] 定义每条交易链路必须携带的 log/metric/trace 字段。
- [ ] 定义 P0/P1 告警、Runbook、critical lag 和 recovery barrier rules。
- [ ] 定义 config hot reload vs restart policy、version activation 和 rollback。
- [ ] 定义 Kill Switch、system mode、leader lease/fencing 和 stale token 行为。
- [ ] 为后续 Control/Observability implementation task 提供验收标准。

## Activation evidence

- On 2026-08-11, a human explicitly authorized starting the next task after TASK-020/PR #74 completed its independent Review and closeout; the coordinator selected TASK-022 as the only backlog/ready candidate.
- TASK-046 remains completed with trusted schema-v1 delivery, passed acceptance, formal independent APPROVE evidence, and a merge commit, satisfying TASK-022's sole dependency gate.
- This PR only activates TASK-022 for Observability, Config, and Control L4 contract work. It does not represent contract completion, implementation completion, Review approval, release authorization, or downstream dependency unlock.
- TASK-021, TASK-023, TASK-025, TASK-027 and all other blocked tasks remain blocked; no task is activated or unlocked by this PR.

## Review focus

- 一笔交易能否从行情到成交完整还原。
- 控制面是否不能绕过 Risk/OMS/Execution。
- 告警是否避免高基数 label。

## Risks and rollback

- 观测不完整会让实盘事故不可复盘；控制面错误会直接影响交易安全。

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
  acceptance_status: passed
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

- [x] 定义每条交易链路必须携带的 log/metric/trace 字段。
- [x] 定义 P0/P1 告警、Runbook、critical lag 和 recovery barrier rules。
- [x] 定义 config hot reload vs restart policy、version activation 和 rollback。
- [x] 定义 Kill Switch、system mode、leader lease/fencing 和 stale token 行为。
- [x] 为后续 Control/Observability implementation task 提供验收标准。

### Acceptance evidence (machine-checked)

- [x] End-to-end observability context, correlation/causation, redaction and bounded metric labels are frozen in `PORTS-CONTROL`, `NFR-OBSERVABILITY`, `CONTRACT-CONTROL-PLANE-V1` and tested by `test_control_contracts.py`.
- [x] P0/P1/P2 alert severity, owner/runbook, critical-lag authority, trigger/recovery windows and recovery-barrier requirements are frozen in `CONTROL-SEMANTIC-VALIDATION-V1` and `WF-CONTROL-PLANE`.
- [x] Config hot-reload/restart boundaries, immutable version/checksum, secret references, prepare/ack, atomic ActiveVersion+Event+Outbox, rollback and UNKNOWN behavior are schema- and semantic-tested.
- [x] Kill switch, system-mode transitions, leader lease/fencing and stale-token rejection are frozen in the event schemas, `SM-SYSTEM-MODE`, `PORTS-CONTROL` and deterministic negative probes.
- [x] TASK-025 references the frozen contract IDs, implementation owner, failure paths and bundle boundary while remaining blocked; no runtime or release behavior is implemented.

## Activation evidence

- On 2026-08-11, a human explicitly authorized starting the next task after TASK-020/PR #74 completed its independent Review and closeout; the coordinator selected TASK-022 as the only backlog/ready candidate.
- TASK-046 remains completed with trusted schema-v1 delivery, passed acceptance, formal independent APPROVE evidence, and a merge commit, satisfying TASK-022's sole dependency gate.
- This PR only activates TASK-022 for Observability, Config, and Control L4 contract work. It does not represent contract completion, implementation completion, Review approval, release authorization, or downstream dependency unlock.
- TASK-021, TASK-023, TASK-025, TASK-027 and all other blocked tasks remain blocked; no task is activated or unlocked by this PR.

## Implementation evidence

- `CONTRACT-CONTROL-PLANE-V1` freezes redacted observability context, bounded alert/runbook DTOs, immutable config candidates/results, kill-switch commands/results, leader lease/fencing and recovery-barrier evidence. `CONTRACT-CONTROL-SEMANTIC-VALIDATION-V1` requires the same fail-closed validator at publish, Outbox persistence, command dispatch, state transition and recovery restore boundaries.
- `PORTS-CONTROL`, `WF-CONTROL-PLANE`, `SM-SYSTEM-MODE`, `NFR-OBSERVABILITY` and `NFR-RELIABILITY` freeze correlation/causation, prohibited sensitive/high-cardinality fields, P0/P1/P2 alert windows, atomic ActiveVersion+Event+Outbox, UNKNOWN reconciliation, stale fencing rejection, kill-switch capacity and recovery-barrier gates.
- Four planned public messages are now registered with Draft 2020-12 schemas and complete disk golden fixture sets: `system.mode_changed.v1`, `system.component_health_changed.v1`, `system.kill_switch_changed.v1`, and `config.version_activated.v1`. Invalid transitions, missing evidence, additional properties, precision/type errors, partial activation, stale lease and incomplete barrier cases are rejected by schema or the normative semantic probe.
- TASK-025 remains `blocked` with its original dependencies and now references the frozen control contracts, implementation owner, failure paths and bundle boundary. No runtime code, migration, monitoring product, OMS state mutation or release was implemented; `implementation_status` remains `in_progress`, `review_status` remains `pending`, and `release_status` remains `prohibited`.
- Acceptance evidence: `poetry run python scripts/validate_specs.py` passed; the control contract suite passes 20 deterministic tests, including the shared `ControlSemanticValidator` combined-envelope matrix for all four events. The repository suite executes 541 passing tests; four unrelated market TZDB tests cannot create Windows temporary directories in the restricted runner and are recorded as an environment-only verification gap.
- Review remediation evidence: `control/control-plane.v1.schema.json` uses Draft 2020-12 `unevaluatedProperties` fail-closed DTO branches; `control/combined-control-message.v1.schema.json` binds the canonical envelope to each mutually exclusive event payload. The shared reference validator enforces source/publisher/partition/aggregate/version/idempotency/fingerprint/correlation/causation, collision, lineage and recursive sensitive-key rules before every normative boundary. `control-semantic-validation.v1.yaml`, `PORTS-CONTROL`, `WF-CONTROL-PLANE`, and TASK-025 freeze config checksum/ack atomicity, kill-switch version/idempotency fencing, recovery-barrier evidence, bounded labels and future runtime integration without claiming current runtime wiring.

## Review focus

- 一笔交易能否从行情到成交完整还原。
- 控制面是否不能绕过 Risk/OMS/Execution。
- 告警是否避免高基数 label。

## Risks and rollback

- 观测不完整会让实盘事故不可复盘；控制面错误会直接影响交易安全。

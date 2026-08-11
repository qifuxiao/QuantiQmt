---
id: TASK-025
title: Implement Control Plane, observability, and recovery gates
status: blocked
depends_on: [TASK-004, TASK-022]
spec_refs: [INV-TRADING, INV-CONSISTENCY, WF-RECOVERY, WF-CONFIG-ACTIVATION, NFR-OBSERVABILITY, NFR-RELIABILITY, CONTRACT-CONTROL-PLANE-V1, CONTRACT-CONTROL-SEMANTIC-VALIDATION-V1, PORTS-CONTROL, WF-CONTROL-PLANE, SM-SYSTEM-MODE]
allowed_paths: [src/quantiqmt/control/**, src/quantiqmt/observability/**, tests/unit/control/**, tests/unit/observability/**, tests/integration/recovery/**]
forbidden_paths: [src/quantiqmt/live/qmt/**, src/quantiqmt/strategy/**]
verification:
  commands:
    - poetry run pytest tests/unit/control tests/unit/observability tests/integration/recovery
    - poetry run mypy src/quantiqmt/control src/quantiqmt/observability
implementation_contract:
  owner: ControlPlane/Observability runtime team after TASK-022 trusted completion
  deliverables:
    - load only the reviewed immutable manifest-indexed control schema bundle; source checkout access is forbidden
    - implement ControlSemanticValidator at command, outbox, publish, transition and recovery-restore boundaries
    - implement redacted correlation-chain logs/traces, bounded metrics and P0/P1/P2 alert runbooks
    - implement atomic config ActiveVersion + config.version_activated.v1 + Outbox with rollback/UNKNOWN reconciliation
    - implement kill-switch CommandBus, lease/fencing and recovery-barrier gates without mutating OMS state
  failure_paths: [stale_fencing_reject, partial_activation_rollback, unknown_command_reconcile, incomplete_barrier_closed, high_cardinality_record_reject]
  review_focus: [envelope_payload_binding, redaction, metric_cardinality, state_transition_guards, atomic_outbox, fail_closed_recovery]
---

# Objective

实现 system mode、kill switch、config activation、leader/fencing、recovery barrier、日志/指标/Trace/告警基础设施。

## Non-goals

- 不实现 Broker 或 Strategy。
- 不允许控制面绕过 Risk/OMS/Execution。

## Acceptance criteria

- [ ] Kill switch 在延迟预算内阻断新风险。
- [ ] Recovery barrier 未打开前拒绝新 OrderIntent。
- [ ] Trading trace 覆盖行情、策略、风控、OMS、Execution、Broker、Trade、Ledger。
- [ ] P0/P1 告警与 critical lag 行为符合规范。

## Review focus

- 控制路径是否拥有保留容量。
- 观测字段是否足以复盘交易。
- 高基数 metric labels 是否被禁止。

## Risks and rollback

- 控制面出错可能导致无法停机或误停机；必须保守。

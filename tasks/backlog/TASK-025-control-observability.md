---
id: TASK-025
title: Implement Control Plane, observability, and recovery gates
status: blocked
depends_on: [TASK-004, TASK-022]
spec_refs: [INV-TRADING, INV-CONSISTENCY, CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ERROR-CATALOG, PORTS-CORE, STORAGE-SOT, WF-RECOVERY, WF-CONFIG-ACTIVATION, NFR-PERFORMANCE, NFR-OBSERVABILITY, NFR-RELIABILITY, CONTRACT-CONTROL-PLANE-V1, CONTRACT-CONTROL-SEMANTIC-VALIDATION-V1, CONTRACT-CONTROL-COMBINED-MESSAGE-V1, PORTS-CONTROL, WF-CONTROL-PLANE, SM-SYSTEM-MODE]
allowed_paths: [src/quantiqmt/control/**, src/quantiqmt/observability/**, tests/unit/control/**, tests/unit/observability/**, tests/integration/recovery/**]
forbidden_paths: [src/quantiqmt/live/qmt/**, src/quantiqmt/strategy/**]
verification:
  commands:
    - poetry run pytest tests/unit/control tests/unit/observability tests/integration/recovery
    - poetry run mypy src/quantiqmt/control src/quantiqmt/observability
implementation_contract:
  owner: ControlPlane/Observability runtime team after TASK-022 trusted completion
  deliverables:
    - package and load the reviewed immutable manifest-indexed control schema bundle
    - implement equivalent typed validation for Control Event, RecoveryPassed, Kill Switch Command, Kill Switch Result and Config Activation boundaries without changing their frozen input facts, order or decisions
    - direct schema-only probes never authorize persist/publish/apply/transition/recovery/side effects
    - validate all four public Events as canonical MessageEnvelopeV1 plus the Control refinement and typed payload, including exact source/type/version/time/idempotency/aggregate binding and minimal AcceptedMessageRef root/non-root lineage
    - use PostgreSQL control_journal as System Mode/Kill Switch authority and component memory only as cache; duplicate decisions use one exact-identity committed Port record and verify its stored-content integrity
    - implement expected-version CAS, stable same-identity replay, QQ-STORAGE-7001 content conflict, and same-identity reconciliation after uncertain commit
    - load immutable config-component and hard-limit inputs plus the exact committed RecoveryBarrierReadPort snapshot and verify scope/reference/checksum/version/generation/lease/fence/complete-evidence/freshness bindings fail-closed
    - implement redacted correlation-chain logs/traces, bounded metrics and P0/P1/P2 alert runbooks
    - implement atomic config ActiveVersion + config.version_activated.v1 + Outbox plus the exhaustive per-component prepare/candidate-effect/rollback-effect APPLIED/REJECTED/PARTIAL/ROLLED_BACK/UNKNOWN internal result matrix, safe-scope, stable result identity and same-identity reconciliation
    - implement scoped Kill Switch CommandBus, lease/fencing and recovery-barrier gates within the NFR latency budget without mutating OMS state
    - restore latest valid System Mode and Kill Switch per scope from control_journal before opening the recovery barrier
    - verify trusted Port provenance, PostgreSQL transaction/CAS/unique-key behavior and uncertain-commit reconciliation in integration tests; raise a separate storage spec-change task before defining any missing Control Journal repository/table contract
    - order component-health transitions by state_version while generation remains instance fencing only
  failure_paths: [stale_fencing_reject, partial_activation_rollback, unknown_command_reconcile, untrusted_persisted_fact_reject, incomplete_barrier_closed, high_cardinality_record_reject, envelope_payload_mismatch, lineage_mismatch, sensitive_field_reject]
  verification:
    - installed_runtime_loads_immutable_manifest_indexed_bundle
    - typed_semantic_validation_runs_before_persist_publish_apply_transition_recovery_side_effect
    - tamper_missing_bundle_and_digest_parity_failure_are_fail_closed
  acceptance:
    - all four control events have envelope+payload binding fixtures and semantic negative matrix
    - config kill_switch recovery_barrier and alert label cross-object invariants are machine validated
  review_focus: [envelope_payload_binding, redaction, metric_cardinality, state_transition_guards, atomic_outbox, fail_closed_recovery, lineage]
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

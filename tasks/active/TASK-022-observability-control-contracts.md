---
id: TASK-022
title: Complete Observability, Config, and Control L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [INV-TRADING, INV-CONSISTENCY, INV-RISK, CONTRACT-MESSAGE-ENVELOPE-V1, CONTRACT-ERROR-CATALOG, PORTS-CORE, SM-SYSTEM-MODE, WF-RECOVERY, WF-CONFIG-ACTIVATION, STORAGE-SOT, NFR-PERFORMANCE, NFR-OBSERVABILITY, NFR-RELIABILITY]
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
  acceptance_status: partial
  review_status: pending
  release_status: prohibited
---

# Objective

冻结日志、指标、Trace、告警、配置激活、Kill Switch、system mode、leader/fencing 和 recovery barrier 的 L4 契约。

## Non-goals

- 不实现监控或控制面代码。
- 不接 Prometheus/Grafana/Alertmanager。
- 不修改交易状态机以绕过控制。
- 不定义 Control Journal 的 Repository、表、内存历史、快照、容量、保留或压缩实现。

## Calibrated trust boundary

- Message/Event/Command/Result wire DTOs are untrusted and require structural, enum, precision, time, scope, identity and integrity validation.
- Immutable domain objects, controlled Port return values and opaque references are operation inputs; they are not recursively self-authenticating JSON facts and need not all be public schemas.
- `control_journal`, `versioned_config_store`, Inbox and Outbox are logical trust anchors. Their source authenticity comes from controlled adapters, committed PostgreSQL transactions, exact query keys, CAS/unique constraints and TASK-025 or independent storage integration tests.
- A checksum/fingerprint proves canonical content integrity or identity, not authorization or source authenticity. Contract probes may corrupt stored content without updating its stored checksum, but do not model an attacker controlling a trusted Port and recomputing every hash.

## Acceptance criteria

- [x] 定义每条交易链路必须携带的 log/metric/trace 字段。
- [x] 定义 P0/P1 告警、Runbook、critical lag 和 recovery barrier rules。
- [x] 定义 config hot reload vs restart policy、version activation 和 rollback。
- [x] 定义 Kill Switch、system mode、leader lease/fencing 和 stale token 行为。
- [x] 为后续 Control/Observability implementation task 提供验收标准。

### Acceptance evidence (machine-checked)

- [x] End-to-end observability context, correlation/causation, redaction and bounded metric labels are frozen in `PORTS-CONTROL`, `NFR-OBSERVABILITY`, `CONTRACT-CONTROL-PLANE-V1` and tested by `test_control_contracts.py`.
- [x] P0/P1/P2 alert severity, owner/runbook, critical-lag authority, trigger/recovery windows and recovery-barrier requirements are frozen in `CONTROL-SEMANTIC-VALIDATION-V1` and `WF-CONTROL-PLANE`.
- [x] Config hot-reload/restart boundaries, immutable version/checksum, secret references and per-component effects are schema- and semantic-tested. Candidate and successful-rollback ActiveVersion changes each use a strictly ordered atomic Event+Outbox transaction; the public Event carries no future ACK claim.
- [x] Kill switch, system-mode transitions, leader lease/fencing and stale-token rejection are frozen in the event schemas, `SM-SYSTEM-MODE`, `PORTS-CONTROL` and deterministic negative probes.
- [x] TASK-025 references the frozen contract IDs, implementation owner, failure paths and bundle boundary while remaining blocked; no runtime or release behavior is implemented.
- [x] RecoveryPassed and Kill Switch OFF consume one exact committed `RecoveryBarrierReadPort` snapshot and bind scope/reference/generation/version, OPEN/opened-at/freshness, lease/fence and complete barrier evidence; stored checksum probes cover corruption detection without claiming source authentication.
- [x] `ConfigActivationResult` has a stable identity/fingerprint and an exhaustive Draft 2020-12 APPLIED/REJECTED/PARTIAL/ROLLED_BACK/UNKNOWN matrix with per-component prepare/candidate-effect/rollback-effect evidence, safe-scope and same-identity reconciliation rules; APPLIED binds the candidate commit and ROLLED_BACK binds the later public restore transaction.
- [x] The four public Event wires bind canonical Envelope fields to payload facts. Non-root lineage consumes a minimal trusted `AcceptedMessageRef`; parent ingress validation and Inbox record authenticity remain their own boundaries.
- [x] Kill/config duplicate probes consume one exact committed Port record, recompute its stored-content fingerprint, return exact late replay before mutable current state, and reject same-identity/different-content. Port provenance/CAS/transaction correctness remains TASK-025 integration work.
- [x] Each active Event retains the fixed six golden fixture categories; actual conditional invariants use only dedicated fixtures or direct tests. Alert-definition and runtime metric-label namespaces remain distinct.

## Activation evidence

- On 2026-08-11, a human explicitly authorized starting the next task after TASK-020/PR #74 completed its independent Review and closeout; the coordinator selected TASK-022 as the only backlog/ready candidate.
- TASK-046 remains completed with trusted schema-v1 delivery, passed acceptance, formal independent APPROVE evidence, and a merge commit, satisfying TASK-022's sole dependency gate.
- This PR only activates TASK-022 for Observability, Config, and Control L4 contract work. It does not represent contract completion, implementation completion, Review approval, release authorization, or downstream dependency unlock.
- TASK-021, TASK-023, TASK-025, TASK-027 and all other blocked tasks remain blocked; no task is activated or unlocked by this PR.

## Implementation evidence

- `CONTRACT-CONTROL-PLANE-V1` freezes redacted observability/alert DTOs, immutable config candidates/results, scoped Kill Switch commands/results, leader lease/fencing, and complete recovery-barrier evidence. It contains no cumulative validation history or storage model.
- The four unreleased Control V1 public payloads are occurred facts. `config.version_activated.v1` describes only an atomic ActiveVersion/Event/Outbox authority change: `CANDIDATE_COMMIT` precedes swap/ACK and `ROLLBACK_RESTORE` follows complete rollback effects. It contains no component ACK/effect claim. `system.kill_switch_changed.v1` describes only a persisted state change; outcome records remain internal result/audit facts.
- `CONTRACT-CONTROL-COMBINED-MESSAGE-V1` directly refines canonical `MessageEnvelopeV1`, uses only its existing fields, and binds each event payload without wire-only `publisher`, `aggregate_type`, or `payload_fingerprint` additions. The shared Envelope file remains unchanged.
- `PORTS-CONTROL`, `WF-CONTROL-PLANE`, `STORAGE-SOT`, and `WF-RECOVERY` establish the authority split: PostgreSQL `control_journal` is durable authority, component memory is cache, and latest valid per-scope System Mode/Kill Switch facts are restored before opening the barrier. TASK-022 does not define the physical Control Journal contract; that remains a separate storage spec-change gap for runtime delivery.
- Kill Switch identity binds type, `scope_type`, `scope_id`, and idempotency key. Duplicate/conflict decisions consume one persisted command/result fact; they do not consume or define a global history structure. Expected-version conflicts use `QQ-COMMON-1003`; only same-identity/different-content uses `QQ-STORAGE-7001`.
- Exact Decimal/I-JSON ingress, configuration security checksum and hard-limit policy binding, component ACK authority, instant-based time comparisons, complete recovery barrier gates, recursive redaction and low-cardinality labels remain frozen.
- Review Calibration removes recursive accepted-fact provenance, full parent payload revalidation and prior-state checks from single wire schemas. The retained probes cover untrusted wire errors, exact Port lookup/content corruption, barrier reference/scope/state/freshness/fence mismatch, minimal parent lineage, and health producer/consumer version responsibilities.
- TASK-025 remains `blocked`, references the final behavior contracts, and no longer requires a giant validator context, one prescribed Python entrypoint, or source-tree/runtime call-graph shape. No runtime code, migration, monitoring product, OMS mutation or release is implemented; delivery stays `in_progress/partial/pending/prohibited`.
- Verification evidence remains partial and is not a full-suite pass. On 2026-08-17 the bare user-level `poetry` launcher failed before collection because its executable is zero bytes. Using the dependency-complete repository `.venv` Poetry executable, the prescribed spec validator passed and the prescribed full pytest command recorded `574 passed / 6 failed`. The same full suite with workspace `--basetemp` also recorded `574 passed / 6 failed`; a sandboxed run against the default Windows `%TEMP%` recorded `570 passed / 6 failed / 4 errors` from that directory's ACL. Control authority/semantic tests passed `51`, and the broader message/control selection passed `277`. The six baseline-existing failures are two expired `2026-08-13` waiver expectations plus four fixture-cleanup cascades. These governance/environment failures are outside TASK-022 paths and are not masked or claimed as passing.
- On 2026-08-24, after the final Config authority-timeline correction, both original bare `poetry run ...` commands still failed before execution because the user-level Poetry launcher could not start. The dependency-complete repository `.venv` Poetry executable passed `scripts/validate_specs.py`; Control/authority tests passed `86`, and message+Control regression passed `317`. The full prescribed `tests/spec tests/contract` selection with a workspace basetemp recorded `614 passed / 6 failed`; the two expired `2026-08-13` waiver assertions are the roots and four same-directory cleanup assertions are cascades. No TASK-022 test failed, but the prescribed suite is not a pass; delivery remains `in_progress/partial/pending/prohibited`.

## Review focus

- 一笔交易能否从行情到成交完整还原。
- 控制面是否不能绕过 Risk/OMS/Execution。
- 告警是否避免高基数 label。

## Risks and rollback

- 观测不完整会让实盘事故不可复盘；控制面错误会直接影响交易安全。

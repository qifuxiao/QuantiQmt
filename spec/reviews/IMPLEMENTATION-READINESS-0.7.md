# Implementation Readiness Review 0.7

> Artifact status: Ready for independent Review; not self-approved
>
> Review date: 2026-08-06
>
> Audited base: `f50d471530fe355e17e7ce82a33a24b8c1b2c01f` (`main`, including merged activation PR #59)
>
> Scope: TASK-017, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022 and TASK-029
>
> Historical predecessor: `REVIEW-IMPLEMENTATION-READINESS-0.5` is preserved unchanged and is not approval evidence for this review.

## Executive decision

The current accepted specification and implementation baseline supports four independently executable L4 contract-definition candidates, two dependency-blocked downstream L4 contract tasks, and one separately evidence-blocked Risk deployment task.

| Task | Decision | Successor/dependency gate | Exact unblock condition |
|---|---|---|---|
| TASK-017 | `ready` candidate; not active | replace historical TASK-014 with TASK-046 | TASK-046 must be completed with trusted delivery evidence, then a human may activate TASK-017 independently |
| TASK-018 | `ready` candidate; not active | replace historical TASK-014 with TASK-046 | TASK-046 must be completed with trusted delivery evidence, then a human may activate TASK-018 independently |
| TASK-019 | `blocked` | replace historical TASK-014 with TASK-046; retain TASK-016 and TASK-018 | TASK-046, TASK-016 and TASK-018 must each have trusted completed delivery; TASK-018 is not completed, so no current unlock |
| TASK-020 | `ready` candidate; not active | replace historical TASK-014 with TASK-046 | TASK-046 must be completed with trusted delivery evidence, then a human may activate TASK-020 independently |
| TASK-021 | `blocked` | replace historical TASK-014 with TASK-046; retain TASK-016, TASK-017 and TASK-020 | TASK-046, TASK-016, TASK-017 and TASK-020 must each have trusted completed delivery; TASK-017/TASK-020 are not completed, so no current unlock |
| TASK-022 | `ready` candidate; not active | replace historical TASK-014 with TASK-046 | TASK-046 must be completed with trusted delivery evidence, then a human may activate TASK-022 independently |
| TASK-029 | `blocked` | retain TASK-015, TASK-030 and TASK-031; TASK-046 is forbidden as a substitute | TASK-030 must first obtain independently reproducible trusted completion evidence through its own remediation path; TASK-046 does not remediate it |

`ready` remains only a backlog candidate label. None of the tasks assessed here is activated, released or authorized for implementation by this Review artifact. Activation is still denied until every direct dependency is completed with schema-v1, passed acceptance, approved/not-required independent Review, merged/not-applicable implementation and trusted completion evidence.

## Authority and baseline audit

The audit applied the repository precedence in this order: safety/trading invariants, Accepted ADR, the manifest-indexed accepted specification, TASK-046, repository instructions, then explanatory documentation. The exact machine-readable inventory and hashes are recorded in `ai/governance/l4-readiness-revalidation-task-046.yaml`.

### Accepted specification baseline

The audited base contains accepted specification version `0.7.0`. Every catalog entry in `spec/manifest.yaml` was reread:

- Invariants: `INV-TRADING`, `INV-CONSISTENCY`, `INV-RISK`.
- Contracts: the message catalog/value/envelope contracts; active Order, Execution, Broker, Ledger, Portfolio, Risk and Strategy schemas; internal Risk/Strategy DTO schemas; and the canonical error catalog.
- Interfaces: `PORTS-CORE`, `PORTS-STRATEGY`, `PORTS-ORDER-PERSISTENCE`, `PORTS-RISK`.
- State machines: Order, Strategy, System Mode, Connection, Account, Portfolio and Reconciliation Case.
- Workflows: Submit, Cancel, Trade Accounting, Broker Reconnect, Config Activation, Strategy Runtime, Order Commit, Outbox Publication and Recovery.
- Repository/storage/NFR: Order Repository, Source of Truth, Order Persistence, Outbox, Performance, Reliability and Observability.
- Reviews: `REVIEW-BASELINE-0.1` and historical `REVIEW-IMPLEMENTATION-READINESS-0.5`.

The accepted contracts establish strong anchors but intentionally leave the reviewed L4 areas unfinished. In particular, the catalog still marks Market, reconciliation/control and several strategy/operations messages as `planned`; `PORTS-CORE` provides only high-level Broker/Market gateway obligations; existing Ledger/Portfolio events do not freeze the full accounting/reconciliation model; and there is no implementation contract for TargetResolver or Backtest/Live adapters.

### Accepted ADR baseline

`docs/ADR/README.md` identifies exactly four Accepted ADRs, all reread for this audit:

- ADR-0001: DDD bounded contexts and contract-first cross-context boundaries.
- ADR-0004: Gateway isolation, interface-first external integration and replaceable adapters.
- ADR-0005: explicit state machines, guarded transitions, audit and recovery.
- ADR-0008: CPython 3.12, immutable typed Domain objects, Decimal, JSON Schema and infrastructure boundaries.

ADR-0002/0003 are superseded in part; ADR-0006/0007 are proposed. They were not promoted to Accepted authority by this task.

### Current implementation baseline

The source tree contains Shared Kernel value types/time, schema registry/message validation, Order Domain, Order persistence/Outbox, Risk model/evaluator/audit/runner and Outbox health policy. It contains no implementation package for Execution/Broker adapters or simulator, Ledger/Portfolio/Reconciliation, TargetResolver, MarketGateway/BarAggregator, Backtest engine/parity adapters, Strategy runtime, or ControlPlane/Observability.

The implementation state therefore does not prove any reviewed L4 area complete. Existing execution/broker/ledger/portfolio JSON schemas and tests are contract anchors only. `SchemaRegistry.project_default()` still reads `spec/contracts` from a source checkout, so TASK-029's deployable-schema problem remains real even though Risk DTO/evaluator/audit code exists.

## Historical governance boundaries

- TASK-014 remains completed only as a historical queue record with `acceptance_status: unverified`, `review_status: reported_unverified` and `release_status: prohibited`. No statement in this review upgrades, repairs or implies its historical approval.
- `REVIEW-IMPLEMENTATION-READINESS-0.5` remains byte-for-byte historical and has status “Draft for TASK-014 Review”; it is context, not trusted successor evidence.
- The retired TASK-014 → TASK-031 bootstrap waiver remains retired. It is not read as an active exception and cannot unlock any business or L4 task.
- TASK-030 remains `reported_unverified` and prohibited. TASK-031's trusted completion and TASK-046's fresh review do not substitute for TASK-030's missing independent evidence.
- TASK-015, TASK-016 and TASK-031 have trusted completed delivery records. Their trust does not automatically activate downstream work.

## Per-task readiness findings

### TASK-017 — ready candidate

Current anchors include `INV-TRADING`, Broker/Execution obligations in `PORTS-CORE`, submit/cancel/unknown workflows, active attempt/unknown/order-report/trade schemas, canonical UNKNOWN/fencing errors and bounded reliability rules. The task has a bounded spec-change outcome: freeze DTOs, capabilities, fencing/deadline/idempotency semantics and a deterministic adverse-condition simulator DSL without implementing runtime code or changing OMS ownership.

The task's future scope is tightened to permit `tests/contract/messages/**`, because deterministic fixtures are an acceptance requirement, while runtime/unit/property/integration code stays forbidden. TASK-006 remains an allowed downstream task update. With this correction, the task can be executed independently after TASK-046 becomes trusted completed delivery.

### TASK-018 — ready candidate

Current anchors include append-only/balanced Ledger invariants, Source of Truth ownership, Trade Accounting workflow, Account/Portfolio/Reconciliation state machines and active trade-posted/position-changed schemas. The task is specifically bounded to freeze double-entry accounts/posting, idempotent trade accounting, position/PnL projection, snapshot/replay and approval-backed adjustment facts; it cannot overwrite OMS/Broker history or implement runtime code.

Future contract fixtures are explicitly allowed while runtime/unit/property/integration code remains forbidden. TASK-007 remains an allowed downstream task update. The task may be independently activated only after TASK-046 has trusted completed delivery.

### TASK-019 — blocked

Strategy Target/OrderIntent schemas and TargetResolver responsibilities exist, and TASK-016 is trusted completed delivery. However InstrumentSpec, active-order expected effect, price/deadband/rounding and position semantics depend on the Ledger/Portfolio contract decisions owned by TASK-018. TASK-018 is only a ready candidate and has no completed delivery evidence.

The historical TASK-014 dependency is replaced by TASK-046 so the downstream queue uses the fresh gate, but TASK-019 remains `blocked`; its TASK-016 and TASK-018 dependencies are retained. It cannot become ready merely because TASK-046 or TASK-018 is active.

### TASK-020 — ready candidate

The contract catalog fixes the four planned market message identities, while `PORTS-CORE`, NFRs and Source of Truth define bounded gateway, quality, snapshot, backpressure and recovery constraints. The task is bounded to activate those schemas, freeze MarketGateway/BarAggregator/session/quality semantics and update the downstream MarketGateway task without implementing a vendor adapter.

Future message fixtures and TASK-023 updates are explicitly allowed; runtime/unit/property/integration code remains forbidden. TASK-020 may be independently activated only after TASK-046 has trusted completed delivery.

### TASK-021 — blocked

Clock and Strategy contracts already define injected/virtual time, no future data and generation fencing, and TASK-016 is trusted completed delivery. Deterministic scheduling, historical availability, execution simulation, fees/slippage and reproducibility nevertheless depend on completed TASK-017 Execution/Broker and TASK-020 Market contracts. Both are only ready candidates.

The historical TASK-014 dependency is replaced by TASK-046, but TASK-017 and TASK-020 are retained. TASK-021 remains `blocked` until all four direct dependencies have trusted completed delivery.

### TASK-022 — ready candidate

The transaction trace, required log/metric fields, prohibited high-cardinality labels, safety alerts, config activation workflow and system-mode/connection state machines are accepted anchors. The task is bounded to freeze missing ControlPlane DTO/events, alert/runbook thresholds, immutable config activation/rollback and lease/fencing/kill-switch behavior without implementing monitoring products or weakening trading controls.

Future message fixtures and TASK-025 updates are explicitly allowed; runtime/unit/property/integration code remains forbidden. TASK-022 may be independently activated only after TASK-046 has trusted completed delivery.

### TASK-029 — blocked independently

TASK-015 and TASK-031 have trusted completed delivery, and current Risk code contains DTO/evaluator/audit/runner behavior. However TASK-030's scope authorization is still `reported_unverified`, and the runtime registry still depends on an explicit/source-checkout schema root rather than a proven installed package route. TASK-029 therefore remains blocked.

TASK-046 is not added as a dependency and cannot be used as remediation for TASK-030. The only safe unblock is independent, auditable remediation of TASK-030 followed by the normal dependency gate and human activation decision.

## Successor dependency migration

| Task | Before | After | Status after migration |
|---|---|---|---|
| TASK-017 | `[TASK-014]` | `[TASK-046]` | `ready` |
| TASK-018 | `[TASK-014]` | `[TASK-046]` | `ready` |
| TASK-019 | `[TASK-014, TASK-016, TASK-018]` | `[TASK-046, TASK-016, TASK-018]` | `blocked` |
| TASK-020 | `[TASK-014]` | `[TASK-046]` | `ready` |
| TASK-021 | `[TASK-014, TASK-016, TASK-017, TASK-020]` | `[TASK-046, TASK-016, TASK-017, TASK-020]` | `blocked` |
| TASK-022 | `[TASK-014]` | `[TASK-046]` | `ready` |
| TASK-029 | `[TASK-015, TASK-030, TASK-031]` | unchanged | `blocked` |

The validator makes this structure fail-closed: all six L4 queue tasks must retain TASK-046 and must not retain TASK-014; TASK-029 must retain TASK-030 and must not add TASK-046. The existing generic activation gate then rejects TASK-046 while active/in-progress, completed but `reported_unverified`, or completed without trusted evidence. Only a completed TASK-046 with passed acceptance, approved independent Review and complete trusted evidence can satisfy the dependency. This still does not auto-activate a ready task.

## Compatibility, migration and rollback

This review and manifest version `0.7.1` change only review registration, task queue metadata, validator policy and spec-test evidence.

- Public message schema changes: none.
- Internal DTO/Port/Repository/Workflow/state-machine changes: none.
- Storage or migration changes: none.
- Error code changes: none.
- Runtime/business code changes: none.
- Release capability: none; prohibited.

Queue migration replaces the untrusted historical readiness edge with TASK-046 for TASK-017/018/019/020/021/022. It does not alter TASK-029's Risk evidence chain. Rollback restores only the review catalog entry, queue dependencies, task-scope corrections and validator/spec-test policy; it must not restore a retired waiver, rewrite TASK-014/TASK-030 evidence, or activate any task.

## Independent Review checklist

- Confirm the exact PR head includes no `src/**`, business schema, Workflow, state-machine, migration, dependency or lockfile changes.
- Confirm TASK-014 and TASK-030 remain `reported_unverified`/prohibited and the waiver registry remains unchanged/retired.
- Confirm each readiness decision follows the current 0.7.0 baseline and implementation tree rather than historical REVIEW-IMPLEMENTATION-READINESS-0.5 claims.
- Confirm TASK-017/018/020/022 remain backlog/ready, TASK-019/021/029 remain backlog/blocked, and none is active.
- Re-run validator/spec/contract tests and bind the independent Review to the exact implementation PR head.
- Do not move TASK-046 to completed until the implementation PR is independently approved, merged and a human separately authorizes closeout evidence.

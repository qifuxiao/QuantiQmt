---
id: TASK-017
title: Complete Execution and Broker simulator L4 contracts
status: active
depends_on: [TASK-046]
spec_refs: [INV-TRADING, PORTS-CORE, WF-SUBMIT-ORDER, WF-CANCEL-ORDER, CONTRACT-EXECUTION-ATTEMPT-STARTED-V1, CONTRACT-EXECUTION-OUTCOME-UNKNOWN-V1, CONTRACT-BROKER-ORDER-REPORTED-V1, CONTRACT-BROKER-TRADE-V1, NFR-RELIABILITY]
allowed_paths: [spec/manifest.yaml, spec/contracts/**, spec/interfaces/**, spec/workflows/**, spec/nfr/**, tests/contract/messages/**, tasks/backlog/TASK-006-broker-simulator.md, tasks/active/TASK-017-execution-broker-contracts.md, tasks/active/README.md, tasks/index.yaml]
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

冻结 ExecutionGateway、BrokerGateway、Broker capabilities、fencing、UNKNOWN、simulator scenario DSL 和 fill/report 语义，使 TASK-006 可实现为后续 Live/Backtest 的共同基准。

## Non-goals

- 不接 MiniQMT。
- 不实现 Execution 或 Simulator 代码。
- 不改变 OMS 状态机。

## Acceptance criteria

- [x] 定义 submit/cancel/query/open_orders/trades/account/positions 的 DTO、deadline、fencing 和 canonical outcomes。
- [x] 定义 Broker capabilities、client_order_id 约束、rate limit 和 idempotency 语义。
- [x] 定义 simulator scenario DSL：accept、reject、partial fill、full fill、duplicate、out-of-order、delay、disconnect、cancel race。
- [x] 定义 simulator deterministic clock/seed 与 contract fixtures。
- [x] 更新 TASK-006，使其不再需要自行发明 Broker/Execution 契约。

## Evidence

- `CONTRACT-EXECUTION-BROKER-GATEWAY-V1` freezes seven request DTOs,
  operation-specific submit/cancel results, five typed `READ_RESULT` variants,
  `BROKER_HEALTH`, Broker capabilities, snapshots, and bounded page responses.
  The BrokerHealth schema exhaustively accepts only HEALTHY with a non-null
  capability version and null reason, DEGRADED with a non-null version and a
  frozen RATE_LIMITED/TRANSPORT_ERROR reason, or DISCONNECTED with a null
  version and DISCONNECTED reason. An executable Cartesian-product probe rejects
  every contradictory status/version/reason combination.
  Golden/negative fixtures reject missing fencing/idempotency/capability version,
  cross-operation confirmations, rejected post-dispatch timeout, typed failure
  payloads, missing rate-limit retry advice, floats, and every negative-zero form.
- `PORTS-CORE` freezes deadline ownership, fencing order, idempotency identity,
  complete read failure returns, client_order_id capability validation, reserved
  rate-limit capacity, unsupported-capability failure, and the rule that
  Execution never advances OMS business state. `PORTS-ORDER-PERSISTENCE` stores
  broker/capability version beside client_order_id; semantic probes independently
  reject all five request/registration/capability version, client-order-ID, and
  broker identity mismatches for both submit and cancel.
- `CONTRACT-BROKER-SCENARIO-V1` and `PORTS-BROKER-SIMULATOR` freeze all nine
  required actions, manual clock/seed inputs, fill/report emission order, and the
  mandatory schema-first semantic validator. Fixtures/probes reject wall-clock
  mode, float fills, unsafe REJECT reasons, ambiguous action fields, sequence
  gaps, forward references, request-operation mismatch, overfill, invalid regex,
  non-matching registered client_order_id, and invalid reserved capacity.
- `WF-SUBMIT-ORDER`, `WF-CANCEL-ORDER`, `WF-BROKER-RECONNECT`, and
  `NFR-RELIABILITY` bind post-dispatch timeout/disconnect to UNKNOWN_OUTCOME,
  reconciliation under the same identities, and blind-retry prohibition.
- TASK-006 now references the frozen contract IDs and contains a bounded
  implementation checklist; it remains blocked and was not activated. TASK-048
  is the blocked owner for the required OrderRegistration runtime/storage binding
  and expand-only migration. Manifest deployment is explicitly ordered
  TASK-017 -> TASK-048 -> TASK-006; historical registrations remain unbound and
  fail closed, and rollback preserves all binding/audit evidence.
- The three named negative fixtures now contain valid `capability_version`
  values. Their contract test repairs only the named defect (missing
  idempotency, missing fence, or float price) and requires the repaired DTO to
  validate, proving no secondary missing field masks the intended failure.
- Verification on 2026-08-07 after the second PR #66 REQUEST_CHANGES
  remediation: `scripts/validate_specs.py` passed and `tests/spec tests/contract`
  passed 285 tests; the focused Ruff, format, diff, and path gates passed. No
  runtime code, MiniQMT
  connection, OMS state-machine change, approval, merge, or completion evidence
  is claimed.

## Review focus

- UNKNOWN 是否禁止盲目重试。
- Simulator 是否模拟真实异常而非只模拟 happy path。
- Execution 是否不能推进订单业务状态。

## Risks and rollback

- 错误模拟器会让后续 Backtest/Live 误信错误语义。

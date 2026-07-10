# Implementation Readiness Review 0.5

> Status: Draft for TASK-014 Review  
> Date: 2026-07-10  
> Scope: TASK-004 through TASK-010, plus missing Phase backlog for multi-agent implementation.

## Executive decision

The queue is not ready for uninterrupted feature implementation yet, but it is now ready to be made implementation-ready in a controlled order.

- TASK-004 is ready to resume implementation after TASK-014 is approved because TASK-013 completed the Order persistence, Journal, Snapshot and transactional Outbox contract.
- TASK-005 and TASK-008 must be blocked. They are conceptually correct, but their Risk and Strategy contracts are not yet precise enough for independent AI Agent implementation.
- TASK-006 through TASK-010 remain blocked and must be re-sequenced behind their missing L4 contract tasks.
- Later phases need explicit backlog tasks for market data, backtest/live parity, observability/control, reconciliation and MiniQMT integration.

## Readiness levels

| Level | Meaning | Required before implementation |
|---|---|---|
| L1 Idea | Goal is described | Not enough |
| L2 Architecture | Components and responsibilities are described | Not enough |
| L3 Engineering | Invariants, events and workflows exist | Maybe enough for architecture review |
| L4 Implementation Specification | DTOs, ports, state, failure modes, tests and acceptance evidence are frozen | Required for Codex/Claude/Gemini implementation |

## Task assessment

| Task | Previous status | New status | Decision |
|---|---:|---:|---|
| TASK-004 Order persistence/outbox | blocked | ready | TASK-013 removed the implementation blocker. It may proceed before Risk/Strategy because it implements OMS persistence, not external Broker behavior. |
| TASK-005 Risk engine | ready | blocked | Missing RiskInput, RuleSet, snapshot DTOs, rule ordering, fail-closed taxonomy and deterministic timing contract. Requires TASK-015. |
| TASK-006 Execution/Broker simulator | blocked | blocked | Missing precise Execution/Broker ports, capability model, scenario DSL and fill semantics. Requires TASK-017 plus TASK-004/TASK-005. |
| TASK-007 Ledger/Portfolio | blocked | blocked | Missing ledger account model, entry taxonomy, cost basis, portfolio snapshot and reconciliation repair contracts. Requires TASK-018. |
| TASK-008 Strategy SDK/runtime | ready | blocked | Missing StrategyContext DTOs, callback/event contracts, checkpoint envelope, generation fencing and resource isolation details. Requires TASK-016. |
| TASK-009 Target resolver | blocked | blocked | Missing instrument spec, price reference, rounding, active-order expected effect and deterministic id algorithm. Requires TASK-019. |
| TASK-010 Reference Buy and Hold | blocked | blocked | Should not mix strategy sample with full end-to-end proof until TargetResolver and Backtest/Live parity are specified. Requires TASK-021. |

## Blocking contract gaps

### Risk

- Define RiskInput with immutable Order snapshot, account snapshot, portfolio snapshot, market snapshot and rule_set_version.
- Define RuleSet ordering, hard system caps, dynamic limits, reduce-only exceptions and stale/partial/timeout taxonomy.
- Define per-rule result DTO and audit payload.
- Define latency measurement source and failure behavior when risk exceeds budget.

### Strategy SDK and runtime

- Define StrategyContext fields as read-only DTOs, not a service locator.
- Define market/order/trade callback event payloads and generation fencing.
- Define checkpoint format, checksum, schema version and restore failure behavior.
- Define output validation, rate limits, resource limits and runtime state transitions.

### Execution and Broker simulator

- Freeze ExecutionGateway and BrokerGateway command/result DTOs.
- Define Broker capabilities, client_order_id acceptance, fencing checks and timeout/UNKNOWN behavior.
- Define simulator scenario DSL for accept/reject/partial fill/duplicate/out-of-order/delay/disconnect.
- Define simulator determinism and contract fixtures.

### Ledger, Portfolio and Reconciliation

- Define double-entry ledger accounts, posting rules, transaction balancing and fee/tax semantics.
- Define position projection, average cost, realized/unrealized PnL policy and snapshot/replay checksum.
- Define reconciliation case payloads, repair command contracts and approval workflow.

### Target Resolver

- Define target scope, mandate, InstrumentSpec, lot/tick rounding, price reference and deadband.
- Define how current holdings and active orders affect target delta.
- Define deterministic intent id/idempotency key generation.

### Market, Backtest/Live and Operations

- Activate market data schemas before implementing Strategy Runtime or Market Gateway.
- Define Backtest/Live parity boundaries: same domain/application logic, replace clock/market/execution only.
- Define metrics/log/trace/alert contracts and kill-switch/config activation behavior before production operations.

## Queue policy

1. Implementation tasks must not require agents to invent DTO, event, repository, workflow or state-machine semantics.
2. If a task discovers a missing contract, stop and create a spec-change task.
3. Feature implementation may only proceed when all direct spec-change dependencies are completed or the active task explicitly allows the missing detail.
4. Every task must have allowed paths, forbidden paths, verification commands, non-goals, acceptance criteria, review focus and rollback/risk notes.

## Resulting order

```text
TASK-004 Order persistence/outbox
TASK-015 Risk contracts → TASK-005 Risk implementation
TASK-016 Strategy contracts → TASK-008 Strategy SDK/runtime
TASK-017 Execution/Broker contracts → TASK-006 Execution/Broker simulator
TASK-018 Ledger/Portfolio/Reconciliation contracts → TASK-007 Ledger/Portfolio
TASK-019 Target Resolver contracts → TASK-009 Target Resolver
TASK-020 Market data contracts → TASK-023 Market Gateway
TASK-021 Backtest/Live parity contracts → TASK-024 Backtest engine
TASK-022 Observability/Control contracts → TASK-025 Control/Observability
TASK-027 Reconciliation engine
TASK-026 MiniQMT live adapters
TASK-010 Reference Buy and Hold only after target/backtest/runtime prerequisites
```

## Compatibility

This review changes task readiness and planning metadata only. It does not change runtime message schemas, persisted storage schemas, public API semantics or existing code.

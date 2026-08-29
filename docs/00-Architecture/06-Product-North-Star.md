# Product North Star

> Status: Human-approved delivery direction (non-normative)
>
> Updated: 2026-08-28
>
> Authority boundary: `spec/` and Accepted ADRs remain authoritative.

## Outcome

QuantiQmt must become a system an operator can start, observe, stop, restart and explain. A release is
not successful merely because it builds as a Python package or has complete contracts. The product
must demonstrate a safe trading path, durable evidence and deterministic replay.

The first visible delivery target is M1: connect the installed Mini QMT client to one exact 模拟账号
and complete a controlled end-to-end order flow. Mini QMT is mandatory for M1. Broker
Simulator remains mandatory for deterministic contract tests and failure injection, but it is not the
user-facing proof that the trading system runs.

## Product invariants

- Strategy produces Target, OrderIntent or CancelIntent and never calls Mini QMT directly.
- Every order follows `OrderIntent → OMS registration → Risk → OMS transition → Execution`.
- PostgreSQL-backed Journal/Outbox and audit evidence precede any external order side effect.
- External uncertainty becomes UNKNOWN and same-identity reconciliation, never blind retry.
- Recovery starts SAFE with a closed barrier and cannot become NORMAL just because a socket connects.
- Money, price, fees and final risk decisions do not use binary float.
- The first account is a simulation account. 真实资金 accounts are outside M1 and remain prohibited.

## Delivery strategy

Deliver thin, executable vertical slices while retaining the safety invariants. Each slice must end in
something observable: a command, a report, a persisted record, a recovery exercise or a Mini QMT
query. Contract work is performed only when it directly unlocks an accepted executable slice or fixes
a demonstrated contract gap.

Near-term slices are:

1. Mini QMT environment/read-only connection probe on the installed client.
2. Durable OMS registration and recovery on PostgreSQL.
3. Deterministic Risk and Execution with Broker Simulator failure tests.
4. Mini QMT simulated-account execution behind account allowlist, Kill Switch and bounded limits.
5. Trade/Ledger/Portfolio projection, restart recovery and reconciliation.
6. Deterministic backtest using immutable Mini QMT-derived historical snapshots.

The machine task queue remains the authorization and dependency authority. This ordering is a product
priority, not permission to skip task dependencies or change `spec/` from implementation code.

## Definition of visible success

An operator can see the configured simulated account, current connection/health mode, funds and
positions; submit one allowlisted minimum-size intent; observe Risk, OMS and Mini QMT reports; restart
the process; recover the same order without duplication; and retrieve a correlation-linked audit trail.
The same strategy and risk policy can run against a checksum-bound historical snapshot under a
VirtualClock and produce reproducible evidence.

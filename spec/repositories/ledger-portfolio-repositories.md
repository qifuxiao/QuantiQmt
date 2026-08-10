# REPO-LEDGER-PORTFOLIO：Ledger、Portfolio 与 Reconciliation Repository 契约

## Ownership and boundaries

- `LedgerRepository` persists AccountLedger accounts and immutable transactions. Ledger Journal is authoritative and append-only.
- `PortfolioRepository` persists rebuildable positions, Portfolio projections, checkpoints and snapshots derived from committed Ledger/Trade facts.
- `ReconciliationRepository` persists Cases, immutable evidence/transitions, repair idempotency and audit. Broker snapshots are evidence only.
- Logical signatures and DTO IDs are frozen by `PORTS-LEDGER-PORTFOLIO`. Infrastructure MUST NOT return ORM entities or expose generic SQL handles.

External Broker/Event Backbone/Redis calls are forbidden inside Repository transactions. All methods are bounded by the caller deadline; timeout or cancellation rolls back the current transaction.

## Ledger append and idempotency

`append_trade` performs, in one PostgreSQL transaction:

1. insert Inbox acceptance for the Broker Trade identity/fingerprint;
2. compare-and-swap the ledger stream head at `expected_ledger_sequence`;
3. insert exactly one `ledger_transactions` row and all balanced `ledger_entries` rows;
4. insert the active public `ledger.trade_posted.v1` Outbox projection and audit evidence.

Before building or appending, `resolve_accounts` resolves every required `(scope_id, currency, account_type, instrument_id)` key against the frozen `account_mapping_version`. The Repository requires exactly one active taxonomy-valid row per key and compares all selected IDs/attributes back to `TradeAccountingRequest.account_selections` in the write transaction. Missing, inactive, duplicate, type/classification/normal-balance or instrument mismatch is fail-closed. It then groups entries by `(scope_id, currency)` and verifies exact Decimal debit/credit equality after the frozen rounding policy. Failure occurs before append.

The unique Trade key is `(broker, account_id, trading_day, trade_id)`. `source_trade.account_id`, request `account_id`, selected Ledger accounts and persisted transaction `account_id` MUST be identical; there is no alternate account alias or implicit mapping. Same key/fingerprint returns the committed `PostResult(outcome=DUPLICATE)` without mutation. Same key/different fingerprint is `QQ-STORAGE-7009`. `transaction_id`, `entry_id` and `(scope_id, ledger_sequence)` are independently unique; a collision inconsistent with the frozen deterministic algorithm is `QQ-STORAGE-7011`, never an idempotent success. `QQ-STORAGE-7006` remains limited to regeneratable random/candidate IDs before side effects and is not returned by deterministic Ledger append.

A CAS mismatch is `QQ-COMMON-1003`; the Application may reread the stream and retry the unchanged input within its original deadline. An uncertain commit returns `UNKNOWN/QQ-STORAGE-7012` with the same transaction/idempotency identity and is queried before any retry. The Repository never changes a deterministic ID or appends a second transaction to escape uncertainty.

`append_adjustment` has all Ledger rules plus a required approved/fresh `RepairCommand`. It atomically binds a discriminated `ADJUSTMENT`/`COMPENSATING_FACT` transaction to unique `(case_id, case_version, command_id, action_id, fact_id)`, canonical `account_id`, command fingerprint, evidence ID, source checkpoint, authorization fingerprint, fencing token, repair-fact checksum and audit ID. It accepts quantity correction and monetary adjustment facts without `source_trade`; a fabricated Trade or mismatched checksum is invalid. Only new facts/transactions/entries may be inserted. UPDATE/DELETE of any historical Ledger row is forbidden.

## Portfolio projection

`apply` accepts one committed `LedgerTransaction` projection change and atomically:

- verifies `expected_source_sequence + 1 == change.source_sequence`;
- verifies `expected_position_version + 1 == after.position_version` and `expected_portfolio_version + 1 == after.portfolio_version`;
- inserts the immutable projection journal/checkpoint;
- compare-and-swaps affected current position and Portfolio rows;
- inserts `portfolio.position_changed.v1` Outbox evidence.

The same `source_ledger_transaction_id` with the same fingerprint is a no-op returning the existing `ProjectionResult`. A different fingerprint is `QQ-STORAGE-7009`. Sequence gap/regression, position/Portfolio version mismatch or stale repair fencing is fail-closed; no projection row, checkpoint or Outbox message changes. An uncertain projection commit is `UNKNOWN/QQ-STORAGE-7013`, queried by the same projection operation identity.

Availability uses the immutable Position `availability_policy_version`. `IMMEDIATE_V1` applies the Trade delta to quantity and availability together. `T_PLUS_ONE_V1` never increases availability on same-day BUY. `release_settlement` validates the exact TradingCalendar version/session evidence, unchanged source checkpoint, expected Position/Portfolio versions, fencing token and `quantity_to_release <= quantity - available_quantity`; it atomically inserts one release identity, applies `quantity_delta=0`, increases availability, increments both versions exactly once, preserves the Ledger checkpoint, and writes audit/Outbox. Same release identity/fingerprint returns its original result without another increment; conflict/out-of-order/unverified/excess/stale CAS is rejected before mutation. Uncertain commit is `UNKNOWN/QQ-STORAGE-7014` and is queried by the same release/idempotency identity. Broker-reported availability cannot invoke either mutation.

Current projections are rebuildable from Ledger. `replay` MUST NOT mutate Ledger or Broker facts. Rebuild replacement is allowed only for the derived current projection after full checksum/sequence verification and uses a single atomic swap guarded by the expected old projection version/checksum. A mismatch opens/updates a Case and returns `QQ-RECOVERY-8003`.

`write_snapshot` first rejects any position/cash/market observation outside the single `snapshot_currency`, then writes only a valid `projection_state_checksum` for an already committed Portfolio version/checkpoint. The checksum covers only Ledger-replayable state; snapshot/valuation envelope and versioned market observations are stored separately. Snapshot failure does not roll back Ledger/Portfolio facts. Invalid snapshots remain diagnostic evidence and are never returned as valid.

## Reconciliation Case and repair

`open_or_append_evidence` uses deterministic `case_id`. First observation inserts version 1/OPEN plus immutable evidence. Re-observation of a non-terminal same key appends evidence and a transition/audit record with CAS version increment. A stale expected version is `QQ-COMMON-1003`; existing facts are not overwritten.

`transition` validates the exact `SM-RECONCILIATION-CASE` pair, guard, expected version, actor and evidence. It atomically inserts transition/audit/Outbox and advances only the Case current projection. Illegal transition is `QQ-RECOVERY-8004`.

`apply_repair` validation order is fixed by `PORTS-LEDGER-PORTFOLIO`. The atomic unit is:

```text
repair_idempotency + appended adjustment/compensating facts +
ledger entries/stream head + projection checkpoint/current rows +
case transition/current version + audit + outbox
```

Every included write commits or all roll back. Reuse of the same idempotency key/fingerprint returns the original result; a fingerprint mismatch is `QQ-STORAGE-7001`. Unauthorized/expired approval is `QQ-RECOVERY-8005`; history mutation is `QQ-RECOVERY-8006`; uncertain commit is `UNKNOWN/QQ-RECOVERY-8007`. An old worker cannot complete or replay a repair after losing its fencing token.

`result_by_idempotency_key` is the sole recovery query after uncertain commit. `UNKNOWN` permits reconciliation of the original command only; a new command, identity, fencing epoch or replacement payload cannot be treated as a retry.

## Canonical result matrix

| Condition | Result | Mutation |
|---|---|---|
| identical Trade/repair replay | original `DUPLICATE` result | none |
| reused key with different fingerprint | `QQ-STORAGE-7001` or `QQ-STORAGE-7009` | none; open Case for Trade conflict |
| stale expected version/sequence | `QQ-COMMON-1003` or `QQ-STORAGE-7010` | none |
| missing/inactive Ledger account | `QQ-STORAGE-7007` | none |
| currency/scope/instrument mismatch | `QQ-STORAGE-7008` | none |
| unbalanced transaction/residual too large | `QQ-STORAGE-7005` | none |
| close/release exceeds verified internal availability or reconciliation difference | `QQ-RECOVERY-8001` | none; Case/evidence only |
| deterministic UUID5 collision | `QQ-STORAGE-7011` | none; Case/evidence only |
| Ledger post commit uncertain | `QQ-STORAGE-7012`, `UNKNOWN` | query same transaction/idempotency identity |
| projection commit uncertain | `QQ-STORAGE-7013`, `UNKNOWN` | query same projection identity |
| settlement release commit uncertain | `QQ-STORAGE-7014`, `UNKNOWN` | query same release/idempotency identity |
| invalid snapshot with intact Ledger | `QQ-STORAGE-7003`, full replay | diagnostic evidence only |
| Ledger gap or replay mismatch | `QQ-RECOVERY-8003` | barrier closed; Case/evidence only |
| illegal Case transition | `QQ-RECOVERY-8004` | none |
| unauthorized/stale repair | `QQ-RECOVERY-8005` | none |
| repair requests history mutation | `QQ-RECOVERY-8006` | none |
| repair commit uncertain | `QQ-RECOVERY-8007`, `UNKNOWN` | query same identity; no blind retry |

Database deadlock/serialization failures may be retried only after full rollback, with bounded attempts inside the original deadline. Semantic conflicts and UNKNOWN are never converted into infrastructure retries.

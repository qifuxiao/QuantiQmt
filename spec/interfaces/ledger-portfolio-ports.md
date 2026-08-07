# PORTS-LEDGER-PORTFOLIO：Ledger、Portfolio 与 Reconciliation Port

本文件冻结 TASK-018 的逻辑签名和跨边界语义。实现可以使用同步或异步 Python Protocol，但不得改变 DTO、幂等、版本、原子性或失败语义。所有集合返回不可变 tuple；Domain/Application DTO 不得包含 ORM、数据库连接、Redis 客户端或 Broker SDK 对象。

## 规范 DTO 来源

- `CONTRACT-LEDGER-ACCOUNTING-V1`（`urn:quantiqmt:internal:ledger-accounting:v1`）：`LedgerAccount`、`TradeAccountingRequest`、`LedgerTransaction`、`LedgerEntry`、`PostResult`。
- `CONTRACT-PORTFOLIO-PROJECTION-V1`（`urn:quantiqmt:internal:portfolio-projection:v1`）：`Position`、`PositionProjectionChange`、`PortfolioSnapshot`、`ReplayRequest`、`ReplayResult`。
- `CONTRACT-RECONCILIATION-V1`（`urn:quantiqmt:internal:reconciliation:v1`）：`ReconciliationCase`、`CaseTransition`、`RepairCommand`、`RepairResult`。
- Public projection events retain `CONTRACT-LEDGER-TRADE-POSTED-V1` and `CONTRACT-PORTFOLIO-POSITION-CHANGED-V1`; they are Outbox projections of committed internal facts, never the persistence model itself.

Implementations MUST run both JSON Schema validation and the semantic validation in this specification before persistence. JSON Schema success alone never proves balance, identity, version, authorization, freshness or checksum validity.

## Ledger account model

`ledger_account_id` is the immutable canonical UUID identity. `account_code` is a unique human/audit code within `(scope_id, currency)` and MUST NOT be used as a foreign key. `scope_id` V1 is the trading-account ledger scope; every account also carries the immutable external `trading_account_id`. Cross-scope posting is forbidden.

| classification | normal balance | V1 account types |
|---|---|---|
| `ASSET` | `DEBIT` | `CASH`, `POSITION_COST` |
| `LIABILITY` | `CREDIT` | reserved; no implementation-selected subtype |
| `EQUITY` | `CREDIT` | `CAPITAL` |
| `INCOME` | `CREDIT` | `REALIZED_PNL` |
| `EXPENSE` | `DEBIT` | `COMMISSION_EXPENSE`, `FEE_EXPENSE`, `TAX_EXPENSE`, `ROUNDING_RESIDUAL` |

Asset/Expense balance is `sum(DEBIT) - sum(CREDIT)`; Liability/Equity/Income balance is `sum(CREDIT) - sum(DEBIT)`. Normal balance is a calculation direction, not an entry restriction: a realized loss is a `DEBIT` to `REALIZED_PNL`. `POSITION_COST` requires one `instrument_id`; every other V1 account has `instrument_id=null`. Account removal is forbidden after reference; deactivation only prevents new postings and preserves replay.

Every transaction MUST contain at least two positive entries and balance exactly for every `(scope_id, currency)` group after quantization: `sum(DEBIT.amount) == sum(CREDIT.amount)`. Zero entries, negative entry amounts, missing/inactive accounts, entry/account instrument mismatch, cross-scope accounts and currency mismatch fail closed before any append. A transaction never performs implicit FX conversion.

## Decimal, precision and rounding

- Money, price, average cost, fee, commission, tax, market value and PnL cross JSON boundaries as canonical plain decimal strings. JSON numbers, binary float, exponent notation, NaN, Infinity and negative zero are forbidden.
- Price and unit average cost have at most 8 fractional digits. V1 Quantity is a non-negative integer; a Trade quantity is positive. Signed changes use an explicit delta field/type, not negative Trade Quantity.
- CNY Ledger amounts use scale 2 and minimum unit `0.01`. The policy ID is `CURRENCY_MINOR_UNIT_HALF_EVEN_V1`; all quantization uses local Decimal context and `ROUND_HALF_EVEN`.
- `gross = quantize(price * quantity, currency_scale)`. Commission, fee and tax are independently quantized before posting. Implementations MUST NOT round an aggregate and infer component values afterward.
- Weighted-average unit cost is retained at scale 8. Monetary cost basis and released cost are quantized at currency scale. A non-zero residual smaller than one currency minimum unit is posted explicitly to the configured `ROUNDING_RESIDUAL` account. A residual at least one minimum unit is `QQ-STORAGE-7005`, not a silently widened adjustment.

## Trade accounting identity and posting

The authoritative trade idempotency tuple is `(broker, account_id, trading_day, trade_id)`. Construct canonical JSON with UTF-8, NFC strings, lexicographic object keys, no whitespace and Decimal scale unchanged. V1 identities are:

```text
transaction_id = UUID5(6ea9f94d-16c3-5c7a-8c4f-ec1883388613, canonical_json(trade_identity_object))
entry_id        = UUID5(transaction_id, "entry:" + zero_based_canonical_entry_ordinal)
idempotency_key = broker + "|" + account_id + "|" + trading_day + "|" + trade_id
```

The fixed namespace is immutable. Entry ordering is the posting-template order below, omitting zero components; implementations MUST NOT sort by generated UUID. `source_fingerprint` is lowercase SHA-256 of the complete validated `broker.trade_reported.v1` payload using the same canonical JSON rules.

- First-seen tuple/fingerprint: build and atomically append one transaction.
- Same tuple and same fingerprint: `DUPLICATE`, returning the original transaction/sequence; no Ledger, Portfolio, Outbox, Inbox or version mutation.
- Same tuple with a different fingerprint: `QQ-STORAGE-7009`; quarantine/open Reconciliation Case and never overwrite the first fact.
- Out-of-order Broker sequence does not change identity or accounting order. An unseen valid trade is posted at the next internal `ledger_sequence`; Broker sequence gaps/staleness are evidence and may open a Case. A trade without a resolved internal `order_id`, account/currency mapping or sufficient position for a close is not posted and remains reconciliation evidence.

V1 cost method is exclusively `WEIGHTED_AVERAGE_V1`; FIFO/LIFO or an implementation-selected method is forbidden.

### BUY posting

```text
DEBIT  POSITION_COST      gross
DEBIT  COMMISSION/FEE     each non-zero quantized component
DEBIT  TAX                non-zero quantized tax
CREDIT CASH               gross + commission + fee + tax
```

New average cost is `(old_cost_basis + gross) / (old_quantity + buy_quantity)`, scale 8, then the monetary cost basis remains the balanced Ledger amount. Buy commission/fee/tax are expenses and reduce net realized PnL; they are not silently capitalized in V1.

### SELL/CLOSE posting

`released_cost = quantize(old_average_cost * close_quantity)`. V1 is long-only and rejects a close exceeding internal quantity. `trade_pnl = gross - released_cost` before expenses.

```text
DEBIT  CASH               gross - commission - fee - tax
DEBIT  COMMISSION/FEE     each non-zero component
DEBIT  TAX                non-zero tax
CREDIT POSITION_COST      released_cost
CREDIT REALIZED_PNL       positive trade_pnl
DEBIT  REALIZED_PNL       absolute negative trade_pnl
```

Only one of the two PnL directions is present. Net realized PnL increment is `trade_pnl - commission - fee - tax`. On full close, quantity and cost basis become zero and average cost becomes null; any permitted sub-minimum residual uses `ROUNDING_RESIDUAL` explicitly.

## Portfolio projection and valuation

Portfolio is derived only from committed Ledger/Trade facts. Broker account/position snapshots are Reconciliation evidence and MUST NOT call a projection write Port or replace internal history.

`position_id` is stable per `(account_id, scope_id, instrument_id, currency, cost_basis_method, availability_policy_version)`. V1 side is `FLAT` or `LONG`; negative/short quantity is not supported by this version. `0 <= available_quantity <= quantity`. Availability policy is immutable for one Position and must be selected by versioned account/instrument configuration before projection; implementation defaults are forbidden:

- `IMMEDIATE_V1`: BUY increases quantity and available quantity together; SELL decreases both and requires `sell_quantity <= before.available_quantity`.
- `T_PLUS_ONE_V1`: same-day BUY increases quantity but not available quantity; SELL decreases both and requires sufficient availability. At a TradingCalendar-confirmed new trading day, prior-day unsettled internal Trade facts are released exactly once through the checkpointed recovery/session projection. If the calendar/checkpoint is unavailable, Portfolio is STALE and availability MUST NOT be increased. Broker availability is reconciliation evidence only.

Every accepted source transaction increments `portfolio_version` exactly once; each affected position increments `position_version` exactly once. `source_sequence` is the contiguous AccountLedger stream sequence and cannot regress or skip during a verified replay. A duplicate transaction changes no version. A T+1 session release is derived deterministically from the prior Ledger checkpoint, increments both versions once, records the unchanged source checkpoint plus the new trading day in projection audit, and is idempotent by `(position_id, trading_day, availability_policy_version)`.

For a fresh market price:

```text
market_value   = quantize(market_price * quantity, currency_scale)
unrealized_pnl = market_value - cost_basis_total
portfolio_equity(currency) = cash(currency) + sum(market_value in currency)
```

Realized PnL is the cumulative net realized PnL from Ledger facts; unrealized PnL uses a market observation with `valuation_at <= PortfolioSnapshot.valuation_time`. No future market data is permitted.

- `FRESH`: price exists within the configured freshness budget; value/PnL present.
- `STALE`: last price and valuation may be retained as explicitly stale evidence, but the snapshot is `PARTIAL_STALE` and `risk_usable=false` for increased risk.
- `MISSING`: price, market value, unrealized PnL and valuation time are null; the snapshot is `UNAVAILABLE` or `PARTIAL_STALE`, and `risk_usable=false`.
- Only `quality=COMPLETE` with all positions freshly valued is usable to increase risk. Degraded snapshots remain readable for diagnostics/risk reduction but never masquerade as fresh.

## Snapshot, checksum and replay

`PortfolioSnapshot` includes `schema_version`, complete cash/position state, `portfolio_version`, valuation quality/time and a `source_checkpoint` containing stream ID, last sequence, transaction ID and transaction checksum.

Canonical JSON V1 uses UTF-8, NFC, lexicographic object keys, no insignificant whitespace, RFC3339 UTC `Z`, Decimal strings unchanged, array order as specified and no float. `checksum = lowercase_hex(SHA-256(canonical_json(snapshot_without_checksum)))`. Positions sort by `(account_id, instrument_id, currency)` and cash sorts by currency before checksum.

Recovery selects the highest supported snapshot not beyond the Ledger head, validates schema/checkpoint/transaction-chain/checksum, then replays strictly contiguous transactions starting at `last_sequence + 1`. `ABSENT` starts full Ledger replay. Corrupt, incompatible or checksum-mismatched snapshots produce `QQ-STORAGE-7003`, are discarded for that recovery attempt and fall back to full verified Ledger replay; they are never silently accepted and a lower snapshot is not substituted in the same attempt. A Ledger gap/checksum-chain failure or replay result/version/checksum mismatch is `QQ-RECOVERY-8003`, closes the recovery barrier and preserves evidence.

## Reconciliation Case and repair

The deterministic Case identity uses canonical JSON of `{broker, account_id, trading_day, scope_id, reason_code}`:

```text
case_id = UUID5(a679b9f2-0619-58dd-8a36-d5bb7c211540, canonical_json(case_key))
```

Re-observing the same open case key appends evidence and increments `case_version`; it does not create parallel cases or overwrite prior evidence. Evidence binds the internal snapshot/checkpoint/checksum and Broker snapshot/observation/sequence, has an expiry, and is immutable. Severity is `P0..P3`; P0/P1 and every MANUAL repair require an independent approval bound to exact case version and evidence ID.

`RepairCommand` is identified by `command_id`; `idempotency_key` is unique. Replay with the same canonical command fingerprint returns the original result. Reuse with another fingerprint is `QQ-STORAGE-7001`. Validation order is: deadline/evidence freshness, authorization, fencing, expected case/portfolio versions, approval, action allow-list, Ledger balance, then append.

Only `APPEND_ADJUSTMENT` and `APPEND_COMPENSATING_FACT` are legal. UPDATE/DELETE/UPSERT of Ledger transactions, entries, Trade facts, Position history, Portfolio history or OMS Order history is `QQ-RECOVERY-8006`. Broker observations never authorize direct overwrite. Automatic repair is limited to policy-whitelisted P2/P3 cases with fresh evidence; P0/P1, ambiguous identity, money/cost differences and UNKNOWN require human approval or investigation.

Repair application atomically commits appended facts, case transition, audit row and Outbox evidence. Any definite failure rolls back all writes. If commit outcome is uncertain, return `UNKNOWN/QQ-RECOVERY-8007`, transition `APPLYING -> UNKNOWN`, keep risk fail-closed and query by the same command/idempotency key; never retry with a new identity. Partial success MUST NOT be reported. `UNKNOWN` can return to investigation only after authoritative outcome reconciliation.

## Logical Ports

```python
class LedgerRepository(Protocol):
    def account(self, ledger_account_id: Identifier, *, deadline_monotonic_ns: int) -> LedgerAccount | None: ...
    def transaction(self, transaction_id: Identifier, *, deadline_monotonic_ns: int) -> LedgerTransaction | None: ...
    def transaction_by_trade(self, trade_identity: TradeIdentity, *, deadline_monotonic_ns: int) -> LedgerTransaction | None: ...
    def append_trade(self, request: TradeAccountingRequest, transaction: LedgerTransaction, outbox: tuple[MessageEnvelope, ...], *, expected_ledger_sequence: int, deadline_monotonic_ns: int) -> PostResult: ...
    def append_adjustment(self, command: RepairCommand, transaction: LedgerTransaction, outbox: tuple[MessageEnvelope, ...], *, expected_ledger_sequence: int, deadline_monotonic_ns: int) -> PostResult: ...
    def read(self, scope_id: str, *, after_sequence: int, page_size: int, page_token: str | None, deadline_monotonic_ns: int) -> LedgerPage: ...

class PortfolioRepository(Protocol):
    def get_position(self, position_id: Identifier, *, deadline_monotonic_ns: int) -> Position | None: ...
    def get_snapshot(self, portfolio_id: Identifier, *, deadline_monotonic_ns: int) -> PortfolioSnapshot | None: ...
    def apply(self, change: PositionProjectionChange, *, expected_position_version: int, expected_portfolio_version: int, expected_source_sequence: int, deadline_monotonic_ns: int) -> Position: ...
    def write_snapshot(self, snapshot: PortfolioSnapshot, *, expected_portfolio_version: int, deadline_monotonic_ns: int) -> None: ...
    def replay(self, request: ReplayRequest, *, deadline_monotonic_ns: int) -> ReplayResult: ...

class ReconciliationRepository(Protocol):
    def get_case(self, case_id: Identifier, *, deadline_monotonic_ns: int) -> ReconciliationCase | None: ...
    def open_or_append_evidence(self, case: ReconciliationCase, *, expected_case_version: int | None, deadline_monotonic_ns: int) -> ReconciliationCase: ...
    def transition(self, transition: CaseTransition, outbox: tuple[MessageEnvelope, ...], *, deadline_monotonic_ns: int) -> ReconciliationCase: ...
    def apply_repair(self, command: RepairCommand, *, deadline_monotonic_ns: int) -> RepairResult: ...
    def result_by_idempotency_key(self, idempotency_key: str, *, deadline_monotonic_ns: int) -> RepairResult | None: ...
```

All pages use `1 <= page_size <= 1000`, opaque tokens and deterministic sequence ordering. A missing object is `None`; storage failure is never disguised as absence. Every operation has a bounded deadline. Exact persistence atomicity and canonical errors are defined by `REPO-LEDGER-PORTFOLIO` and `STORAGE-LEDGER-PORTFOLIO`.

## Observability contract

Every rejected/post/repair/replay result logs the canonical error/outcome, contract/schema version, correlation ID, immutable business identity, expected/actual version or checksum when applicable, and audit/evidence ID; raw sensitive account payloads are not logged. Required counters are `ledger_post_total{outcome,code}`, `portfolio_projection_total{outcome,code}`, `portfolio_replay_total{snapshot_status,code}`, `reconciliation_case_transition_total{from,to,code}` and `reconciliation_repair_total{outcome,code}`. Required gauges/histograms are Ledger/Portfolio checkpoint lag, oldest open Case age by severity, UNKNOWN repair count and bounded operation latency. Balance failure, checksum/replay mismatch, P0/P1 Case and UNKNOWN repair emit an alertable audit event; metrics/logs never substitute for durable facts.

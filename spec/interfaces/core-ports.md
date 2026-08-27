# PORTS-CORE：核心 Port 契约

## BrokerGateway

`ExecutionGateway` is the application boundary used by OMS to request an execution
attempt. `BrokerGateway` is the adapter boundary used by Execution to communicate
with one broker account. Both boundaries use
`CONTRACT-EXECUTION-BROKER-GATEWAY-V1`; implementations MUST NOT replace these
DTOs with broker-specific dictionaries.

```python
class ExecutionGateway(Protocol):
    def submit_order(self, request: SubmitOrderRequest) -> OperationResult: ...
    def cancel_order(self, request: CancelOrderRequest) -> OperationResult: ...
    def query_order(self, request: QueryOrderRequest) -> ReadResult[OrderSnapshot | None]: ...
    def open_orders(self, request: OpenOrdersRequest) -> ReadResult[OrderPage]: ...
    def trades(self, request: TradesRequest) -> ReadResult[TradePage]: ...
    def account(self, request: AccountRequest) -> ReadResult[AccountSnapshot]: ...
    def positions(self, request: PositionsRequest) -> ReadResult[PositionPage]: ...

class BrokerGateway(ExecutionGateway, Protocol):
    def connect(self, *, deadline_at: datetime) -> None: ...
    def disconnect(self, *, deadline_at: datetime) -> None: ...
    def capabilities(self, *, deadline_at: datetime) -> BrokerCapabilities: ...
    def health(self, *, deadline_at: datetime) -> BrokerHealth: ...
```

Every request MUST carry an absolute UTC `deadline_at`; adapters MUST derive a
bounded monotonic wait at ingress and MUST NOT extend it. Submit and cancel MUST
also carry the persisted execution `attempt_id`, the registration's immutable
`capability_version`, a positive `fencing_token`, a stable `idempotency_key`,
and the registered `client_order_id`. The tuple
`(broker, account_id, operation, idempotency_key)` identifies one external
operation. Reuse with a different payload is a definite local rejection. Replay
with the same payload MUST preserve the same idempotency_key and client_order_id
and MUST NOT create a second external order or cancel.

Execution MUST NOT own or advance OMS business state. It persists/executes an
attempt and returns evidence; only OMS merges a canonical result, order report,
or trade into the order aggregate using its expected-version and state-machine
guards. Query snapshots are reconciliation evidence, never an instruction for
Execution to mutate OMS state.

### Canonical operation outcomes

| outcome | side effect possible | reconcile | permitted reasons |
|---|---:|---:|---|
| `CONFIRMED` | true | false | `BROKER_ACCEPTED`, `BROKER_CANCELED` |
| `REJECTED` | false | false | `BROKER_REJECTED`, `INVALID_REQUEST`, `UNSUPPORTED_CAPABILITY`, `RATE_LIMITED`, `STALE_FENCING_TOKEN`, `DEADLINE_EXCEEDED_BEFORE_DISPATCH`, `DISCONNECTED_BEFORE_DISPATCH` |
| `UNKNOWN_OUTCOME` | true | true | `TIMEOUT_AFTER_DISPATCH`, `DISCONNECTED_AFTER_DISPATCH`, `TRANSPORT_UNCERTAIN` |

The adapter MUST determine whether dispatch may have occurred. A deadline or
disconnect before dispatch is `REJECTED`; once dispatch may have occurred, any
timeout, disconnect, cancellation of the local wait, malformed response, or
transport ambiguity is `UNKNOWN_OUTCOME` (`QQ-EXEC-6003` for submit and
`QQ-EXEC-6004` for cancel). UNKNOWN MUST open reconciliation and MUST NOT be
retried by changing `attempt_id`, `idempotency_key`, or `client_order_id`.
Reconciliation queries use the same client_order_id and broker/account scope.

Every `query_order`, `open_orders`, `trades`, `account`, and `positions` call
MUST return the schema-defined `ReadResult`; routine dependency failures MUST
NOT escape as implementation-selected exceptions or ad-hoc nulls. A confirmed
result contains only the payload selected by its operation (`query_order` alone
may return `NOT_FOUND/null`). A rejection has `payload=null` and one of
`INVALID_REQUEST`, `UNSUPPORTED_CAPABILITY`, `RATE_LIMITED`,
`DEADLINE_EXCEEDED`, `DISCONNECTED`, or `TRANSPORT_ERROR`. `RATE_LIMITED`
requires bounded `retry_after_ms`; all other reasons require null. Read failures
have no external mutation, are fail-closed, and never authorize an OMS state
change. `BrokerHealth` is the versioned `BROKER_HEALTH` DTO with this exhaustive
state matrix; adapters MUST NOT emit any other combination:

| status | capability_version | reason_code |
|---|---|---|
| `HEALTHY` | required, non-null | null |
| `DEGRADED` | required, non-null | `RATE_LIMITED` or `TRANSPORT_ERROR` |
| `DISCONNECTED` | null | `DISCONNECTED` |

`reason_code` is the frozen enum `null`, `RATE_LIMITED`, `TRANSPORT_ERROR`, or
`DISCONNECTED`, not adapter-selected text. `capability_version` identifies the
snapshot actually observed while connected; a disconnected adapter cannot
claim that an unobserved/current snapshot remains authoritative. Every health
DTO also carries its broker identity and UTC observation time.

Fencing validation happens before idempotency lookup and before every external
side effect. A stale token is `REJECTED/STALE_FENCING_TOKEN` and maps to
`QQ-EXEC-6006`; it cannot return cached success from an older leader.

### Capabilities and rate limits

Capabilities are an immutable, versioned snapshot. Execution MUST validate the
operation, order type, time-in-force, position effect, and client_order_id
length/regular expression/case rules against the same `capability_version` used
to register the order. Unsupported behavior is rejected before dispatch as
`UNSUPPORTED_CAPABILITY`; adapters MUST NOT emulate or silently downgrade it.
`min_length <= max_length`; the configured pattern MUST accept the registered
ID. A changed capability version requires revalidation, not mutation of an
already-dispatched identity.

Order registration MUST persist the selected `broker` and
`broker_capability_version` beside `client_order_id`. Before either submit or
cancel dispatch, the mandatory semantic validator MUST compare the request,
persisted registration, and selected immutable capability snapshot and require
all five bindings:

- `request.capability_version == registration.broker_capability_version`;
- `capability.capability_version == registration.broker_capability_version`;
- `request.client_order_id == registration.client_order_id`;
- `request.broker == registration.broker`;
- `capability.broker == registration.broker`.

Any missing or mismatched binding is `REJECTED/UNSUPPORTED_CAPABILITY` before
fencing/idempotency dispatch. No ambient adapter state, current capability
lookup, or side channel may supply or overwrite any identity for an existing
order. Implementations MUST run the schema validator and this complete semantic
validator; validating only the two capability-version fields is non-conforming.

A legacy registration whose persisted `broker` and
`broker_capability_version` are both null is explicitly `UNBOUND`. A partial
null/non-null pair is invalid persisted data. `UNBOUND` and invalid bindings
MUST fail closed before dispatch and remain available only for recovery and
reconciliation evidence. TASK-048 cannot repair or infer them; any future
binding requires a separately reviewed, append-only repair contract.

Gateway DTO schema validation MUST run before a capability semantic validator.
That validator MUST compile the declared regular expression before activation
and reject invalid syntax, `min_length > max_length`, a registered ID whose
length or full-string match violates the frozen constraint, or
`reserved_cancel + reserved_reconciliation > burst`; it MUST NOT repair the
snapshot or infer broker defaults.

The declared token bucket has `requests_per_second`, `burst`, and strictly
positive reserved capacity for cancel and reconciliation. Submit traffic MUST
NOT consume `reserved_cancel` or `reserved_reconciliation`. Exhaustion before
dispatch returns `REJECTED/RATE_LIMITED` with bounded `retry_after_ms`; callers
may retry only a definitely non-dispatched request before its original deadline.
UNKNOWN is never converted into a rate-limit retry.

All prices, balances, values, costs, commission, and tax use canonical decimal
strings with at most 8 fractional digits. JSON numbers are forbidden for those
fields. Collection methods are bounded by `page_size <= 1000`, use opaque page
tokens, and return a stable broker-defined order within one reconciliation run.

## MarketGateway

MUST 提供 start/stop、subscribe/unsubscribe、snapshot、health。订阅幂等；回调只标准化并有界入队；Snapshot 包含 as_of、quality、version。

## EventPublisher/EventSubscriber

PublishReceipt 只表示 Backbone 接收。Subscriber 只有业务事务提交后 ACK；重投必须依赖 Inbox 幂等。Subscription 必须指定 consumer_name、event_types、partition、max_in_flight、retry 和 replay policy。

## CommandBus

MUST 提供明确接收者、deadline 和 CommandResult。MUST NOT 使用 EventBus request/response 模拟需要确定结果的下单、撤单和控制动作。

## Clock/Scheduler

Clock 提供 UTC business time 和 monotonic latency time。Scheduler Command 必须具有 job_id、misfire policy 和 idempotency_key。Domain MUST NOT 直接读取系统时间。

规范性逻辑签名及解释见 `docs/15-Interfaces/API-Contracts.md`；若该文档与本规范冲突，以本规范为准。

# PORTS-MARKET: Market data and MarketGateway contract

## Authority and validation

`CONTRACT-MARKET-DATA-V1` and the four public market event schemas are the only
normative DTO shapes. Implementations MUST run Draft 2020-12 validation followed
by the semantic validation in this specification before publishing, storing, or
feeding Strategy/Risk. Vendor dictionaries are confined to the adapter.

The semantic validator MUST reject timestamp inversion, source/watermark
regression, duplicate identity with different content, invalid gap ranges,
quality/reason mismatch, an unresolved gap represented as `NORMAL`, calendar or
session version mismatch, illegal session transitions, invalid OHLC, cross-session
aggregation, late mutation after finality, and checksum mismatch.

## MarketGateway

```python
class MarketGateway(Protocol):
    def start(self, request: LifecycleRequest) -> LifecycleResult: ...
    def stop(self, request: LifecycleRequest) -> LifecycleResult: ...
    def subscribe(self, request: SubscriptionRequest) -> SubscriptionResult: ...
    def unsubscribe(self, request: SubscriptionRequest) -> SubscriptionResult: ...
    def snapshot(self, request: SnapshotRequest) -> SnapshotResult: ...
    def health(self, request: HealthRequest) -> MarketHealth: ...
```

`LifecycleRequest`, `SubscriptionRequest`, `SnapshotRequest`, and `HealthRequest`
are schema-frozen in `CONTRACT-MARKET-DATA-V1`. Every operation carries an
absolute UTC `deadline_at`; an implementation derives a bounded monotonic wait
without extending the deadline. Mutating operations also carry `generation`,
positive `fencing_token`, and stable `idempotency_key`.
`(subscription_id, generation, operation)` is the subscription identity. Exact
replay returns `IDEMPOTENT_REPLAY`; reuse with different instruments, event types,
capacity, or policy is `REJECTED/INVALID_REQUEST`. Older generation/fencing is
rejected before any side effect. Outcomes are exhaustive:

| outcome | permitted reason |
|---|---|
| `APPLIED` | `SUBSCRIBED`, `UNSUBSCRIBED` |
| `IDEMPOTENT_REPLAY` | `ALREADY_APPLIED` |
| `REJECTED` | `INVALID_REQUEST`, `STALE_GENERATION`, `STALE_FENCING`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` |

The schema additionally binds operation-specific success: START/APPLIED uses
`STARTED`, STOP/APPLIED uses `STOPPED`, SUBSCRIBE/APPLIED uses `SUBSCRIBED`, and
UNSUBSCRIBE/APPLIED uses `UNSUBSCRIBED`; contradictory combinations are invalid.
`SnapshotResult` is either `AVAILABLE/AVAILABLE` with a non-null validated
snapshot or `REJECTED` with null snapshot and exactly one of
`DEADLINE_EXCEEDED`, `UNAVAILABLE`, `STALE`, `GAP`, `INVALID_REQUEST`.
Request/result identifiers and generation/operation fields MUST match.

The callback boundary may only normalize validated vendor data and perform a
non-blocking bounded enqueue. It MUST NOT perform blocking I/O, persistence,
Strategy/Risk evaluation, calendar inference, or unbounded allocation.

`queue_capacity`, `batch_capacity`, warning and critical watermarks are finite and
schema-bound. `REJECT_NEW` emits `DEGRADED/BACKPRESSURE`. Controlled coalescing is
allowed only for supersedable quote observations and MUST emit deterministic
`GAP/CONTROLLED_DROP` evidence with the exact source-sequence range. Trades,
session events, quality events, audit messages, and already-final bars MUST NOT be
dropped or coalesced. Market queues never share capacity with transaction/audit
queues.

## Snapshot and health

A snapshot binds `instrument_id`, `as_of`, `snapshot_version`, `source_sequence`,
`calendar_version`, `session_id`, quality, unresolved-gap count and checksum.
`NORMAL` requires `stale=false` and zero unresolved gaps. STALE, GAP, RECOVERING,
UNAVAILABLE or a failed checksum is fail-visible and MUST NOT satisfy a fresh
Strategy/Risk input request.

Health is exhaustive and bound to `HealthRequest.request_id`: `HEALTHY` requires
`NORMAL/OK`; `DEGRADED` permits `DEGRADED`, `STALE`, `GAP`, or `RECOVERING` with
the corresponding frozen degraded reason; `DISCONNECTED` requires `UNAVAILABLE`
and `UNAVAILABLE` or `DISCONNECTED`. Queue depth/capacity and source lag are
mandatory. A deadline or adapter failure is returned as fail-visible health or
snapshot rejection; null and thrown adapter exceptions are not Port outcomes.

## Trading calendar and session

`TradingCalendar` is versioned, checksum-bound authority for exchange timezone,
trading day, UTC session intervals and local-midnight crossing. Domain code uses
an injected Clock and MUST NOT infer trading day from UTC date or environment
timezone. Intervals are ordered, non-overlapping and never inferred from ticks.

Session states are `CLOSED`, `PRE_OPEN`, `OPEN`, `BREAK`, `CLOSING`. The public
session schema enumerates every legal state pair. A duplicate is represented only
as `CLOSED -> CLOSED / DUPLICATE_SUPPRESSED`; an old transition sequence is ignored
with audit evidence and cannot move state. Calendar-version mismatch is rejected.

## MarketQuality

Priority is `UNAVAILABLE > GAP > STALE > RECOVERING > DEGRADED > NORMAL`. A worse
state dominates simultaneous evidence. Enter/exit reasons are schema-frozen.
Strategy and Risk consume the same quality event and MUST fail closed according to
their accepted snapshot policies.

Receiving one newer item never restores `NORMAL`. Recovery requires: reconnect;
version-matched snapshot; bounded backfill; contiguous source sequences;
calendar/session match; verified checkpoint/checksum; zero unresolved gaps; then
`RECOVERING -> NORMAL / RECOVERY_VERIFIED`. An irrecoverable gap remains GAP or
UNAVAILABLE and stays observable.

## BarAggregator

Input is the normalized tick identity and uses the public Decimal-string rules.
Policy binds timeframe, calendar version, event-time windows, allowed lateness,
duplicate/out-of-order handling, empty-window and session-break behavior.

- duplicate same identity/same content is ignored; different content fails closed;
- out-of-order data within allowed lateness is buffered until the injected
  watermark; watermark MUST NOT regress;
- data after a final bar is rejected and emits gap evidence; final history is never
  silently revised;
- windows never cross session intervals or breaks; empty windows emit no bar;
- GAP produces a partial, quality-tagged bar only when evidence is preserved;
- OHLCV/turnover, sequence range, watermark, identity and checksum are validated.

For identical normalized input order, calendar/version, policy, checkpoint and
watermark sequence, LIVE and REPLAY MUST emit byte-identical payload identity,
checksum and ordering. Wall clock, environment time and ambient randomness are
forbidden; future-event reads are forbidden.

## Observability and failures

Logs include provider, operation, quality/reason, calendar/session version,
generation, queue ratios and error classification. Metrics/alerts are defined in
NFR-PERFORMANCE/NFR-OBSERVABILITY and MUST NOT label instrument, message,
correlation, order or account identifiers. All failures are explicit; no adapter
exception, null, silent drop or guessed calendar state is a valid contract result.

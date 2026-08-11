# PORTS-MARKET: Market data and MarketGateway contract

## Authority and validation

`CONTRACT-MARKET-DATA-V1`, `CONTRACT-MARKET-SEMANTIC-VALIDATION-V1`, and the four
public market event schemas are the only normative DTO shapes and validation
rules. Implementations MUST run Draft 2020-12 validation, envelope/payload binding,
then the shared semantic validator before publish, persistence, quality transition,
snapshot restore, or Strategy/Risk delivery. A failure forbids repair-in-place,
publish, persistence, state advance, and restoration. Vendor dictionaries are
confined to the adapter.

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
schema-bound; the semantic ordering is
`warning < critical < overflow <= queue_capacity`, and queue depth cannot exceed
capacity. V1 freezes `REJECT_NEW_WITH_GAP_EVIDENCE`; Tick coalescing is forbidden
because Tick quantity/turnover are incremental facts. Overflow rejects the new
item, enters visible `GAP/DEGRADED`, and emits the exact lost source-sequence
range. Trades, session events, quality events, audit messages, and final bars are
never dropped or coalesced. Market queues never share capacity with
transaction/audit queues.

## Snapshot and health

A snapshot binds provider, generation, instrument, calendar/session,
source/source-sequence, quality version, aggregation-policy version, `as_of`,
quality, unresolved-gap count and JCS checksum. `AVAILABLE` requires
`NORMAL`, `stale=false`, zero unresolved gaps, a verified checksum, and exact
request/snapshot version binding. STALE, GAP, RECOVERING, UNAVAILABLE, an
unverified checksum, or any binding mismatch returns non-AVAILABLE with the
schema-frozen reason and cannot satisfy Strategy/Risk.

Health is exhaustive and bound to request ID, provider, generation,
calendar/session, source/quality version and effective policy version. `HEALTHY`
requires `NORMAL/OK`, queue depth below warning, and source lag below the frozen
stale threshold. `DEGRADED` uses the exact quality/reason matrix;
`DISCONNECTED` requires `UNAVAILABLE`. Serious queue pressure, lag, threshold
inconsistency, or depth above capacity cannot be HEALTHY. A deadline or adapter
failure is returned as fail-visible health or snapshot rejection; null and thrown
adapter exceptions are not Port outcomes.

## Envelope binding and idempotency

The complete per-event matrix is machine-indexed by
`CONTRACT-MARKET-SEMANTIC-VALIDATION-V1`. It binds message type/version,
publisher source, partition, aggregate identity/version, message ID,
idempotency identity, occurrence/receive times, and every payload identity field.
Envelope and payload being separately schema-valid is insufficient.

Idempotency identity never contains a payload hash. The validator separately
computes the RFC 8785 JCS SHA-256 payload fingerprint. Same identity and same
fingerprint is a duplicate; same identity and different fingerprint is a
fail-closed collision. Collision evidence is retained for reconciliation and
cannot be bypassed with a new arbitrary identity.

## Trading calendar and session

`TradingCalendar` is versioned, checksum-bound authority for exchange timezone,
trading day, UTC session intervals and local-midnight crossing. Domain code uses
an injected Clock and MUST NOT infer trading day from UTC date or environment
timezone. Intervals are ordered, non-overlapping and never inferred from ticks.

Session states are `CLOSED`, `PRE_OPEN`, `OPEN`, `BREAK`, `CLOSING`. The public
session schema enumerates every legal state pair. A duplicate is represented only
as `CLOSED -> CLOSED / DUPLICATE_SUPPRESSED`; an old transition sequence is ignored
with audit evidence and cannot move state. Calendar-version mismatch is rejected.
Timezone must be an IANA name supported by the deployed calendar database.
The validator proves each UTC interval's local trading-day mapping and
`crosses_local_midnight` flag, and proves each aggregation input event time lies
inside its bound half-open session interval.

## MarketQuality

Priority is `UNAVAILABLE > GAP > STALE > RECOVERING > DEGRADED > NORMAL`. A worse
state dominates simultaneous evidence. Enter/exit reasons are schema-frozen.
Strategy and Risk consume the same quality event and MUST fail closed according to
their accepted snapshot policies.

Quality events bind calendar ID, trading day, previous/current quality and source
versions. Quality version increases by exactly one; source version never regresses;
the complete previous/current/reason matrix is machine indexed. Receiving one
newer item never restores `NORMAL`. Recovery evidence is a structured binding of
snapshot/checkpoint identity and checksum, backfill/gap ranges, calendar/session,
watermark and previous/current versions. Ranges must be provable from the source
versions. Only verified contiguous recovery may transition
`RECOVERING -> NORMAL / RECOVERY_VERIFIED`. An irrecoverable gap remains GAP or
UNAVAILABLE and stays observable. Strategy rejects new input and Risk treats the
snapshot as invalid whenever quality is non-NORMAL, stale, unavailable, or has an
unresolved gap.

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

Ticks are deterministically ordered by `(event_time, source_sequence, event_id)`.
Open/close are first/last prices in that order; high/low are Decimal maxima/minima;
volume is the exact sum of incremental integer quantity and turnover is the exact
sum of incremental Decimal-string turnover with no rounding. Windows align to
`session_open + n * timeframe_seconds`, have exact timeframe length, and cannot
cross a break/session. Final event time equals window end and its watermark event
time covers window end plus allowed lateness.

Calendar, Snapshot, Checkpoint and Bar checksums use the exact projections in the
semantic contract, RFC 8785 JCS, UTF-8 without BOM and SHA-256 lowercase hex.
Decimal values remain strings and Unicode is not normalized. Bar `event_id` is
UUIDv5 using namespace `9a41e905-11f3-5c30-8f02-5ba3f8ae8485` and the indexed JCS
identity projection; history cannot be silently revised by selecting UUID4.

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

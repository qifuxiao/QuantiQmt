# PORTS-BACKTEST: Backtest/Live parity Ports

`CONTRACT-BACKTEST-PARITY-V1` and
`CONTRACT-BACKTEST-PARITY-SEMANTIC-V1` freeze the Backtest adapter boundary.
Backtest and Live MUST execute the same Domain, Application, Strategy,
TargetResolver, Risk, OMS, Ledger and Portfolio logic. Only Clock, Market,
Execution, Scheduler and storage adapters may differ. A Backtest adapter MUST
NOT expose a second order path or mutate OMS, Ledger or Portfolio state directly.

## VirtualClock

```python
class VirtualClock(Protocol):
    def state(self) -> VirtualClockState: ...
    def utc_now(self) -> datetime: ...
    def monotonic_ns(self) -> int: ...
    def advance_to(
        self, run_id: UUID, target_at: datetime, *, deadline_monotonic_ns: int
    ) -> VirtualClockState: ...
```

The clock starts at `BacktestRunSpec.start_at`; `monotonic_ns` is exactly
`elapsed_us * 1000` and is not the host monotonic clock. `advance_to` may advance
only to the earliest admitted Scheduler event, may never regress or skip an
earlier key, and never moves past `end_at`. Strategy callbacks cannot hold this
Port. Domain and Strategy code MUST NOT read the host wall clock.

A host monotonic watchdog MAY terminate a hung process, but it produces a failed
run with retained evidence; it MUST NOT select a business branch or turn a run
into `COMPLETED`.

## DeterministicScheduler

```python
class DeterministicScheduler(Protocol):
    def schedule(
        self, event: SchedulerEvent, *, deadline_monotonic_ns: int
    ) -> SchedulerResult: ...
    def cancel(
        self, run_id: UUID, event_id: UUID, idempotency_key: str,
        *, deadline_monotonic_ns: int
    ) -> SchedulerResult: ...
    def peek(self, run_id: UUID, *, deadline_monotonic_ns: int) -> SchedulerEvent | None: ...
    def pop_due(
        self, run_id: UUID, current_at: datetime, *, max_items: int,
        deadline_monotonic_ns: int
    ) -> tuple[SchedulerEvent, ...]: ...
```

The queue is finite and configured by an immutable Scheduler policy. Its exact
ordering key is `(dispatch_at, priority, source_id ASCII bytes, source_sequence,
causal_sequence, event_id)`. The event type/priority mapping is frozen in the
Semantic Contract. Process scheduling, insertion races, locale, hash order and
ambient randomness are forbidden ordering inputs.

Exact idempotency replay returns `IDEMPOTENT_REPLAY`; identity reuse with
different content is `REJECTED/INVALID_EVENT`. An event inserted while another
event is executing may use the same virtual timestamp only when its complete key
sorts strictly after the current key. Queue overflow rejects the new event and
fails the run visibly; it never drops, coalesces or reorders admitted events.

`event_id` is UUIDv5 over the run UUID and the SHA-256/JCS fingerprint of every
other scheduler identity/content field, so it never depends on insertion order.
Canceling a pending event returns `CANCELED`; an exact repeated cancel returns
`IDEMPOTENT_REPLAY/ALREADY_CANCELED`. Unknown or already-dispatched events return
`REJECTED/EVENT_NOT_FOUND` or `REJECTED/EVENT_ALREADY_DISPATCHED`; cancellation
never rewrites the admitted event journal.

## HistoricalMarketPort

```python
class HistoricalMarketPort(Protocol):
    def open(
        self, run: BacktestRunSpec, manifest: HistoricalDatasetManifest,
        *, deadline_monotonic_ns: int
    ) -> None: ...
    def read(
        self, request: HistoricalReadRequest, *, virtual_now: datetime,
        deadline_monotonic_ns: int
    ) -> HistoricalReadResult: ...
    def close(self, run_id: UUID, *, deadline_monotonic_ns: int) -> None: ...
```

The Port reads an immutable, checksum-verified dataset manifest. A page may
contain only events whose recorded `available_at` is not after both the request
bound and current VirtualClock. Event time is not availability time. Bar OHLCV
is unavailable until the final Bar event itself is available; correction and
corporate-action facts apply only at their recorded availability.

The result is always the schema-frozen `PAGE`, `WAIT`, `END` or `REJECTED`
envelope. When no row is currently visible but later data exists, `WAIT` exposes
only an opaque cursor and the earliest recorded `next_available_at` to the
Backtest coordinator. The coordinator admits a priority-5 `HISTORICAL_RELEASE`
wakeup at that time, advances the VirtualClock normally, then reads again. The
hint cannot expose payload, price, volume, future partition content, or enter a
Strategy/context/business branch. This wakeup rule prevents an empty Scheduler
at run start from terminating before the first historical event. `WAIT` is valid
only when the hint is within `run.end_at`; otherwise the result is
`END/END_OF_RUN_RANGE` with no cursor or hint.

The wakeup has `contract_id=CONTRACT-BACKTEST-PARITY-V1`,
`source_id=HISTORICAL_MARKET`, source sequence zero, and a payload checksum over
only `(run_id, manifest_checksum, next_cursor, next_available_at)`. Its
idempotency key is `history-release:<payload_checksum>`; a duplicate hint is an
exact Scheduler replay, not another wakeup.

Routine failures do not escape as implementation-selected exceptions or bare
nulls. Cursors are opaque, stable, bound to the manifest checksum and reveal no
future rows or partition metadata to Strategy code. Before Scheduler admission,
each referenced artifact is loaded from the immutable installed bundle and
validated as the same public Market MessageEnvelope/Payload used by Live.

## ExecutionSimulatorPort

```python
class ExecutionSimulatorPort(ExecutionGateway, Protocol):
    def configure(
        self, run: BacktestRunSpec, policy: ExecutionSimulationPolicy,
        scenario: BrokerScenarioV1, *, deadline_monotonic_ns: int
    ) -> None: ...
```

The simulator consumes the exact `CONTRACT-EXECUTION-BROKER-GATEWAY-V1` request
DTOs and emits only the existing `broker.trade_reported.v1` and
`broker.order_reported.v1` payloads. It has no OMS Repository and never advances
OMS state. Submit/Cancel fencing, capability binding, idempotency, UNKNOWN and
reconciliation semantics remain those of `PORTS-CORE` and
`PORTS-BROKER-SIMULATOR`.

Matching uses only a released Market fact whose Scheduler key is strictly after
the confirmed-submit cutoff and whose candidate Trade time is strictly after the
Order acceptance time. `NEXT_TICK_V1` uses the next released tradeable Tick;
`NEXT_BAR_OPEN_V1` may use a final Bar only when that Bar is available and emits
the report after the configured latency. An order accepted during a Bar cannot be
retroactively filled at that Bar's earlier Open. Strategy cannot observe that Bar
before release. Orders do not match outside an OPEN session or against non-NORMAL,
untradeable, GAP, STALE or unavailable Market evidence.

Slippage is adverse (`BUY` adds, `SELL` subtracts), then rounded to Tick (`BUY`
ceiling, `SELL` floor). The adjusted Price must independently satisfy the limit
and inclusive price band; clamping is forbidden. Quantity uses only released
incremental volume, the configured participation cap and leaves quantity.
When multiple orders compete for one fact, allocation is exactly by confirmed
acceptance Scheduler key and then canonical internal `order_id`; the fact's
incremental-volume budget is decremented once and never reused across orders.

The immutable Broker scenario controls gateway acceptance/rejection, delay,
disconnect and report-delivery faults. Scenario actions that declare their own
fill quantity or price (`PARTIAL_FILL`, `FULL_FILL`, or `CANCEL_RACE`) are invalid
for this market-matching profile; only released Market facts plus the execution
policy may create a fill. `DUPLICATE`/`OUT_OF_ORDER` may reference an already
generated report group but cannot alter identity or payload. `DAY` expires at
session close, `IOC` evaluates one eligible released fact then cancels leaves,
and `FOK` fills all leaves on its first eligible fact or cancels without a Trade.
Unsupported or ambiguous order/TIF combinations fail before side effect.
Cancel/fill races follow already-admitted canonical Scheduler order: a confirmed
cancel prevents any new match, an already admitted Trade/report is immutable,
and OMS alone resolves final state from the existing Broker reports.

Commission uses `PER_ORDER_CUMULATIVE_DELTA_V1`: each fill charges only the
difference between the cumulative required commission and commission already
charged, so a minimum commission is never charged once per partial fill.
Transfer fee and sell tax are computed per fill from exact Decimal Notional. All
components are independently quantized to the currency minor unit using
`CURRENCY_MINOR_UNIT_HALF_EVEN_V1`. The generated Trade binds those values to
`commission`, `fee` and `tax`. Floats, implicit zero fees, future volume and
ambient randomness are forbidden.

Gateway deadlines are evaluated against VirtualClock only. A required causal
report, expiration, cancellation or timer whose deterministic dispatch would be
after `BacktestRunSpec.end_at` fails the run as `END_BOUNDARY_UNSETTLED`; it is
never silently truncated and cannot produce `COMPLETED` evidence.

## BacktestStoragePort

```python
class BacktestStoragePort(Protocol):
    def begin_run(
        self, run: BacktestRunSpec, *, deadline_monotonic_ns: int
    ) -> BacktestRunSpec: ...
    def append_event(
        self, run_id: UUID, event: SchedulerEvent, canonical_fact: bytes,
        *, deadline_monotonic_ns: int
    ) -> None: ...
    def commit_evidence(
        self, evidence: BacktestRunEvidence, *, deadline_monotonic_ns: int
    ) -> BacktestRunEvidence: ...
    def get_by_input_fingerprint(
        self, input_fingerprint: str, *, deadline_monotonic_ns: int
    ) -> tuple[BacktestRunSpec, BacktestRunEvidence | None] | None: ...
```

This adapter is isolated from production data and preserves the same UoW,
Journal, Inbox/Outbox, Snapshot checksum and append-only behavior required by the
shared application. It cannot replace those transitions with a final-state
assignment. Run specs, admitted event facts, failures and evidence are append-only.
An uncertain commit is reconciled by the same run/input identity and is never
restarted under a new identity. TASK-021 defines no physical table or migration.

## ParityHarness

```python
class ParityHarness(Protocol):
    def compare_shared_logic(
        self, live_trace: ArtifactRef, backtest_trace: ArtifactRef,
        *, deadline_monotonic_ns: int
    ) -> ParityComparison: ...
    def compare_recorded_trace_replay(
        self, recorded_live_trace: ArtifactRef, replay_evidence: BacktestRunEvidence,
        *, deadline_monotonic_ns: int
    ) -> ParityComparison: ...
```

`SHARED_LOGIC` compares callback inputs, Strategy outputs, Target resolution,
Risk decisions and OMS business transitions while making no claim that a future
Live Broker outcome equals a simulation. `RECORDED_TRACE_REPLAY` replays already
recorded external facts at their recorded availability and additionally compares
causal order and final Ledger/Portfolio checksums.

Normalization may remove host/process/connection identity, wall-duration and
adapter telemetry. It MUST retain business/message identity, correlation,
causation, available/business times, Decimal strings, outcomes, reasons, error
codes, versions and checksums. `MATCH` requires equal normalized checksums, zero
mismatches and zero future reads. A Backtest or parity match is evidence only and
never production approval.

## Dependency and security boundary

The dependency direction is:

```text
strategy -> strategy_sdk -> shared contracts
backtest adapters -> shared application Ports
shared Domain/Application -X-> backtest adapters
```

Strategies never receive Clock mutation, Scheduler mutation, Historical cursors,
ExecutionSimulator, storage, Broker, SQL, Redis, filesystem or network clients.
The only order path remains:

```text
Target/OrderIntent -> OMS registration -> Risk -> OMS transition -> ExecutionGateway
-> Broker reports -> OMS merge -> Ledger/Portfolio
```

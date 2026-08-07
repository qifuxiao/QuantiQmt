# PORTS-BROKER-SIMULATOR: deterministic scenario contract

`CONTRACT-BROKER-SCENARIO-V1` is the only normative input DSL for the programmable
Broker Simulator. It models BrokerGateway behavior; it never imports OMS, writes
an Order aggregate, or advances an OMS business state.

## Deterministic inputs and ordering

A run is a pure function of the validated scenario, signed 63-bit `seed`, manual
clock state, and ordered gateway requests. System wall time, process scheduling,
hash randomization, locale, and ambient randomness are forbidden inputs. The
clock starts at `clock.start_at`; only the harness may advance it in integer
microseconds. Identical inputs MUST produce byte-identical gateway results,
`broker.order_reported.v1`, and `broker.trade_reported.v1` payloads.

Steps have unique, contiguous `sequence` values starting at 1. After schema
validation and before consuming the first step, the mandatory semantic validator
MUST validate the scenario together with the ordered gateway request stream and
the frozen BrokerCapabilities snapshot. It rejects gaps, duplicates, forward
references, unknown source sequences, step/request count mismatch, a step whose
`on_operation` does not equal the consumed request operation, and partial/race
fill quantity exceeding that request's positive remaining quantity.

The same semantic gate MUST compile the capability's client_order_id regular
expression, reject invalid syntax, verify `min_length <= max_length`, and require
the persisted registered client_order_id to satisfy length and full-string match
under the declared case-sensitivity rule. It also preserves PORTS-CORE's
reserved-capacity invariant. Validation is fail-closed: no step, clock advance,
random draw, or simulated side effect occurs after any validation error.

Emissions are ordered by `(scheduled_clock_us, step.sequence, emission_index)`.
The default fill action emits `broker.trade_reported.v1` at emission index 0 and
the cumulative `broker.order_reported.v1` at index 1. `OUT_OF_ORDER` explicitly
reorders already-created emissions according to `source_sequences`; `DUPLICATE`
copies the original identity and payload rather than inventing a new report or
trade ID. Consumers still MUST be duplicate- and out-of-order-safe.

## Actions

- `ACCEPT`: confirms submit and emits an ACCEPTED order report.
- `REJECT`: definitely rejects before side effect using only `BROKER_REJECTED`,
  `INVALID_REQUEST`, `UNSUPPORTED_CAPABILITY`, `RATE_LIMITED`,
  `STALE_FENCING_TOKEN`, `DEADLINE_EXCEEDED_BEFORE_DISPATCH`, or
  `DISCONNECTED_BEFORE_DISPATCH`. Post-dispatch timeout/disconnect/transport
  reasons are invalid for this action and must use `DISCONNECT`/`DELAY` UNKNOWN
  semantics instead.
- `PARTIAL_FILL`: emits a positive bounded fill and cumulative order report.
- `FULL_FILL`: fills exactly the remaining quantity.
- `DUPLICATE`: emits `copies` byte-identical copies of a prior emission group.
- `OUT_OF_ORDER`: emits prior groups in the exact listed order.
- `DELAY`: advances only the manual clock by `duration_us`; deadline classification
  follows whether dispatch has occurred.
- `DISCONNECT`: `BEFORE_DISPATCH` is definite rejection;
  `AFTER_DISPATCH`/`BEFORE_RESPONSE` are UNKNOWN and require reconciliation.
- `CANCEL_RACE`: deterministically chooses `FILL`, `CANCEL`, or
  `PARTIAL_FILL_THEN_CANCEL`; facts are emitted in the declared canonical order
  and OMS alone resolves the resulting state.

For a repeated idempotency tuple with an identical request, the simulator
replays the stored external identity and outcome without consuming another
side-effecting step. A different request under that tuple is an idempotency
conflict with no side effect. Stale fencing, unsupported capability, and rate
limit scenarios follow PORTS-CORE and execute before a side-effecting action.

## Failure and rollback boundary

Invalid scenario/schema/semantic input fails closed before the first simulated
side effect. Exhausted steps fail the run rather than falling back to a happy
path. Rollback means removing the scenario activation and its generated
ephemeral simulator state; published reports or audit evidence are immutable and
must never be rewritten.

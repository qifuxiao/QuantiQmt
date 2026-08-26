from __future__ import annotations

from datetime import UTC, datetime

from quantiqmt.market.gateway import InMemoryMarketGateway
from quantiqmt.market.policy import AcceptedPolicyStore
from quantiqmt.market.validation import SNAPSHOT_PROJECTION, projection_checksum

NOW = datetime(2026, 8, 11, 1, 30, tzinfo=UTC)


class Clock:
    def now(self) -> datetime:
        return NOW


POLICY = {
    "dto_type": "MARKET_VALIDATION_POLICY",
    "schema_version": 1,
    "provider": "SIM",
    "generation": 1,
    "calendar_id": "CN-A",
    "calendar_version": "cal-v1",
    "session_id": "am",
    "policy_version": "market-policy-v1",
    "aggregation_policy_version": "bar-v1",
    "activated_at": "2026-08-11T00:00:00Z",
    "snapshot_max_age_ms": 1000,
    "future_clock_skew_ms": 100,
    "queue_capacity": 4,
    "warning_watermark": 1,
    "critical_watermark": 2,
    "overflow_watermark": 3,
    "source_lag_stale_ms": 2000,
    "tzdb_version": "2026c",
    "policy_checksum": "",
}


def request(operation: str = "SUBSCRIBE", *, key: str = "subscribe-key-0001") -> dict[str, object]:
    return {
        "dto_type": "SUBSCRIPTION_REQUEST",
        "schema_version": 1,
        "operation": operation,
        "subscription_id": "550e8400-e29b-41d4-a716-446655440040",
        "provider": "SIM",
        "generation": 1,
        "fencing_token": 1,
        "idempotency_key": key,
        "deadline_at": "2026-08-11T01:31:00Z",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "source_version": 0,
        "quality_version": 1,
        "policy_version": "market-policy-v1",
        "instruments": ["600000.XSHG"],
        "event_types": ["TICK", "QUALITY"],
        "queue_capacity": 4,
        "batch_capacity": 2,
        "warning_watermark": 1,
        "critical_watermark": 2,
        "overflow_watermark": 3,
        "source_lag_stale_ms": 2000,
        "overflow_policy": "REJECT_NEW_WITH_GAP_EVIDENCE",
    }


def tick(sequence: int) -> dict[str, object]:
    return {
        "event_id": f"550e8400-e29b-41d4-a716-{sequence:012d}",
        "partition_key": "600000.XSHG",
        "provider": "SIM",
        "instrument_id": "600000.XSHG",
        "exchange": "XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "trading_day": "2026-08-11",
        "event_time": "2026-08-11T01:30:00Z",
        "received_at": "2026-08-11T01:30:00.001Z",
        "source_sequence": sequence,
        "watermark_sequence": sequence,
        "last_price": "10.01",
        "last_quantity": 100,
        "turnover": "1001.00",
        "quality": "NORMAL",
        "gap_start_sequence": None,
        "gap_end_sequence": None,
    }


def gateway() -> InMemoryMarketGateway:
    policy = dict(POLICY)
    AcceptedPolicyStore.refresh_checksum(policy)
    store = AcceptedPolicyStore()
    store.activate(policy)
    return InMemoryMarketGateway(clock=Clock(), policies=store)


def snapshot_request() -> dict[str, object]:
    return {
        "dto_type": "SNAPSHOT_REQUEST",
        "schema_version": 1,
        "request_id": "550e8400-e29b-41d4-a716-446655440042",
        "provider": "SIM",
        "generation": 1,
        "instrument_id": "600000.XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "source_version": 0,
        "quality_version": 1,
        "aggregation_policy_version": "bar-v1",
        "deadline_at": "2026-08-11T01:31:00Z",
    }


def health_request() -> dict[str, object]:
    return {
        "dto_type": "HEALTH_REQUEST",
        "schema_version": 1,
        "request_id": "550e8400-e29b-41d4-a716-446655440043",
        "provider": "SIM",
        "generation": 1,
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "source_version": 0,
        "quality_version": 1,
        "policy_version": "market-policy-v1",
        "deadline_at": "2026-08-11T01:31:00Z",
    }


def test_subscribe_and_unsubscribe_are_idempotent() -> None:
    subject = gateway()
    first = subject.subscribe(request())
    replay = subject.subscribe(request())
    conflict = subject.subscribe(request(key="different-key-0002"))

    assert (first["outcome"], first["reason_code"]) == ("APPLIED", "SUBSCRIBED")
    assert (replay["outcome"], replay["reason_code"]) == (
        "IDEMPOTENT_REPLAY",
        "ALREADY_APPLIED",
    )
    assert (conflict["outcome"], conflict["reason_code"]) == ("REJECTED", "INVALID_REQUEST")

    stopped = subject.unsubscribe(request("UNSUBSCRIBE", key="unsubscribe-key01"))
    stopped_replay = subject.unsubscribe(request("UNSUBSCRIBE", key="unsubscribe-key01"))
    assert stopped["reason_code"] == "UNSUBSCRIBED"
    assert stopped_replay["outcome"] == "IDEMPOTENT_REPLAY"


def test_callback_is_nonblocking_bounded_and_overflow_is_gap_visible() -> None:
    subject = gateway()
    subject.subscribe(request())

    assert [
        subject.on_tick(request()["subscription_id"], 1, 1, tick(i)).accepted for i in range(1, 4)
    ] == [
        True,
        True,
        True,
    ]
    rejected = subject.on_tick(request()["subscription_id"], 1, 1, tick(4))

    assert rejected.accepted is False
    assert rejected.reason_code == "OVERFLOW_REJECTED"
    assert rejected.gap_start_sequence == rejected.gap_end_sequence == 4
    subject.apply_gap_evidence("600000.XSHG", rejected)
    assert subject.quality("600000.XSHG").quality == "GAP"
    assert subject.queue_depth(request()["subscription_id"]) == 3


def test_drain_delivers_bounded_backfill_to_the_quality_pipeline() -> None:
    subject = gateway()
    subscription_id = request()["subscription_id"]
    subject.subscribe(request())

    assert subject.on_tick(subscription_id, 1, 1, tick(5)).accepted is True
    subject.drain(subscription_id)
    assert subject.quality("600000.XSHG").contiguous_source_version == 0

    for sequence in range(1, 5):
        assert subject.on_tick(subscription_id, 1, 1, tick(sequence)).accepted is True
        subject.drain(subscription_id)

    state = subject.quality("600000.XSHG")
    assert state.quality == "GAP"
    assert (state.contiguous_source_version, state.highest_observed_sequence) == (5, 5)


def test_snapshot_and_health_are_validated_before_every_return() -> None:
    subject = gateway()
    subject.subscribe(request())
    snapshot = {
        "dto_type": "MARKET_SNAPSHOT",
        "schema_version": 1,
        "provider": "SIM",
        "generation": 1,
        "instrument_id": "600000.XSHG",
        "calendar_id": "CN-A",
        "calendar_version": "cal-v1",
        "session_id": "am",
        "as_of": "2026-08-11T01:30:00Z",
        "source_version": 0,
        "source_sequence": 0,
        "quality_version": 1,
        "aggregation_policy_version": "bar-v1",
        "quality": "NORMAL",
        "stale": False,
        "unresolved_gap_count": 0,
        "checksum_verified": True,
    }
    snapshot["content_checksum"] = projection_checksum(snapshot, SNAPSHOT_PROJECTION)
    subject.put_snapshot(snapshot)

    assert subject.snapshot(snapshot_request())["outcome"] == "AVAILABLE"
    health = subject.health(health_request())
    assert (health["status"], health["quality"], health["reason_code"]) == (
        "DEGRADED",
        "DEGRADED",
        "SOURCE_LAG",
    )

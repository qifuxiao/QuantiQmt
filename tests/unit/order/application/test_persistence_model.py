from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from quantiqmt.messaging.outbox import (
    CriticalOutboxLagPolicy,
    OutboxLagSnapshot,
    evaluate_outbox_safety,
)
from quantiqmt.order.application.persistence import (
    ClaimPolicy,
    JournalAppend,
    OrderRegistration,
    OrderRegistrationDraft,
    OrderSnapshot,
    PersistedOrder,
    canonical_json_bytes,
    deterministic_message_id,
    order_state_payload,
    registration_fingerprint,
    snapshot_checksum,
)
from quantiqmt.order.domain import Order
from quantiqmt.shared import Identifier, InstrumentId, Price, Quantity

ORDER_ID = Identifier("550e8400-e29b-41d4-a716-446655440000")
INTENT_ID = Identifier("550e8400-e29b-41d4-a716-446655440001")
NOW = datetime(2026, 7, 10, 1, 2, 3, tzinfo=UTC)


def registration() -> OrderRegistration:
    return OrderRegistration(
        order_id=ORDER_ID,
        intent_id=INTENT_ID,
        client_order_id="client-1",
        account_id="account-1",
        instrument_id=InstrumentId("600000.XSHG"),
        side="BUY",
        position_effect="AUTO",
        order_type="LIMIT",
        quantity=Quantity(100),
        limit_price=Price("10.01000000"),
        time_in_force="DAY",
        owner_strategy_id="strategy-1",
        owner_strategy_version="v1",
        registered_at=NOW,
    )


def test_registration_draft_has_no_client_order_id_and_requires_utc() -> None:
    draft = OrderRegistrationDraft(
        order_id=ORDER_ID,
        intent_id=INTENT_ID,
        account_id="account-1",
        instrument_id=InstrumentId("600000.XSHG"),
        side="BUY",
        position_effect="AUTO",
        order_type="MARKET",
        quantity=Quantity(100),
        limit_price=None,
        time_in_force="DAY",
        owner_strategy_id="strategy-1",
        owner_strategy_version="v1",
        registered_at=NOW,
    )
    assert not hasattr(draft, "client_order_id")
    with pytest.raises(FrozenInstanceError):
        draft.account_id = "other"  # type: ignore[misc]


def test_canonical_json_is_stable_and_rejects_float() -> None:
    left = canonical_json_bytes({"b": "é", "a": ("1.2300", 1)})
    right = canonical_json_bytes({"a": ("1.2300", 1), "b": "e\u0301"})
    assert left == right
    assert b"1.2300" in left
    with pytest.raises(TypeError, match="float"):
        canonical_json_bytes({"bad": 1.0})  # type: ignore[dict-item]


def test_registration_fingerprint_preserves_decimal_scale() -> None:
    base = {"intent_id": INTENT_ID.value, "limit_price": "10.0100", "tags": {"a": "b"}}
    changed_scale = {"intent_id": INTENT_ID.value, "limit_price": "10.01", "tags": {"a": "b"}}
    assert registration_fingerprint(base) != registration_fingerprint(changed_scale)


def test_state_payload_contains_recovery_collections_in_deterministic_order() -> None:
    reg = registration()
    persisted = PersistedOrder(
        reg,
        Order(ORDER_ID, Quantity(100)),
        registration_fingerprint({"intent_id": INTENT_ID.value}),
    )
    payload = order_state_payload(persisted)
    assert payload["aggregate_version"] == 1
    assert payload["registration_fingerprint"] == persisted.registration_fingerprint
    assert payload["processed_facts"] == []
    assert payload["broker_sequences"] == []
    assert payload["registration"]["limit_price"] == "10.01000000"  # type: ignore[index]


def test_journal_payload_is_immutable_and_rejects_json_float() -> None:
    append = JournalAppend(
        journal_id=Identifier("550e8400-e29b-41d4-a716-446655440002"),
        order_id=ORDER_ID,
        aggregate_version=1,
        event_type="ORDER_REGISTERED",
        payload={"post_state": {"aggregate_version": 1}},
        occurred_at=NOW,
        correlation_id="correlation-0001",
    )
    with pytest.raises(TypeError):
        append.payload["x"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="float"):
        JournalAppend(
            journal_id=Identifier("550e8400-e29b-41d4-a716-446655440003"),
            order_id=ORDER_ID,
            aggregate_version=1,
            event_type="ORDER_REGISTERED",
            payload={"bad": 1.0},  # type: ignore[dict-item]
            occurred_at=NOW,
            correlation_id="correlation-0001",
        )


def test_claim_policy_bounds_and_deterministic_message_id() -> None:
    with pytest.raises(ValueError):
        ClaimPolicy(0, 1000, 1, 10, 10, "2", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 999, 1, 10, 10, "2", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 101, 10, 10, "2", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 60001, 60001, "2", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 10, 3600001, "2", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 10, 10, "1", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 10, 10, "10.1", "0")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 10, 10, "2", "-0.1")
    with pytest.raises(ValueError):
        ClaimPolicy(1, 1000, 1, 10, 10, "2", "1.1")
    first = deterministic_message_id("oms.order_registered.v1", ORDER_ID.value, 1)
    second = deterministic_message_id("oms.order_registered.v1", ORDER_ID.value, 1)
    assert first == second
    assert len(first) == 64


def test_outbox_safety_evaluator_rejects_new_risk_on_critical_lag_or_dead_letters() -> None:
    policy = CriticalOutboxLagPolicy(critical_lag_ms=10_000, critical_dead_letter_count=0)

    healthy = evaluate_outbox_safety(
        OutboxLagSnapshot(
            oldest_order_message_lag_ms=9_999,
            order_dead_letter_count=0,
            pending_order_message_count=1,
        ),
        policy,
    )
    lagged = evaluate_outbox_safety(
        OutboxLagSnapshot(
            oldest_order_message_lag_ms=10_000,
            order_dead_letter_count=0,
            pending_order_message_count=1,
        ),
        policy,
    )
    dead_lettered = evaluate_outbox_safety(
        OutboxLagSnapshot(
            oldest_order_message_lag_ms=1,
            order_dead_letter_count=1,
            pending_order_message_count=1,
        ),
        policy,
    )

    assert healthy.reason_code == "OK"
    assert healthy.reject_new_risk is False
    assert lagged.reject_new_risk is True
    assert lagged.emit_health_alert is True
    assert lagged.reason_code == "ORDER_OUTBOX_LAG_CRITICAL"
    assert dead_lettered.reject_new_risk is True
    assert dead_lettered.reason_code == "ORDER_OUTBOX_DEAD_LETTER_CRITICAL"


def test_snapshot_checksum_covers_all_fields_except_checksum() -> None:
    payload = {"order_id": ORDER_ID.value, "aggregate_version": 1}
    base = OrderSnapshot(
        Identifier("550e8400-e29b-41d4-a716-446655440010"),
        ORDER_ID,
        1,
        1,
        payload,
        "a" * 64,
        "0" * 64,
        NOW,
    )
    digest = snapshot_checksum(base)
    same_with_different_checksum = OrderSnapshot(
        base.snapshot_id,
        base.order_id,
        base.aggregate_version,
        base.schema_version,
        base.state_payload,
        base.journal_head_checksum,
        "f" * 64,
        base.created_at,
    )

    assert snapshot_checksum(same_with_different_checksum) == digest
    assert (
        snapshot_checksum(
            OrderSnapshot(
                Identifier("550e8400-e29b-41d4-a716-446655440011"),
                base.order_id,
                base.aggregate_version,
                base.schema_version,
                base.state_payload,
                base.journal_head_checksum,
                base.snapshot_checksum,
                base.created_at,
            )
        )
        != digest
    )
    assert (
        snapshot_checksum(
            OrderSnapshot(
                base.snapshot_id,
                Identifier("550e8400-e29b-41d4-a716-446655440012"),
                base.aggregate_version,
                base.schema_version,
                base.state_payload,
                base.journal_head_checksum,
                base.snapshot_checksum,
                base.created_at,
            )
        )
        != digest
    )
    assert (
        snapshot_checksum(
            OrderSnapshot(
                base.snapshot_id,
                base.order_id,
                2,
                base.schema_version,
                {"order_id": ORDER_ID.value, "aggregate_version": 2},
                base.journal_head_checksum,
                base.snapshot_checksum,
                base.created_at,
            )
        )
        != digest
    )
    assert (
        snapshot_checksum(
            OrderSnapshot(
                base.snapshot_id,
                base.order_id,
                base.aggregate_version,
                base.schema_version,
                {"order_id": ORDER_ID.value, "aggregate_version": 1, "state": "REGISTERED"},
                base.journal_head_checksum,
                base.snapshot_checksum,
                base.created_at,
            )
        )
        != digest
    )
    assert (
        snapshot_checksum(
            OrderSnapshot(
                base.snapshot_id,
                base.order_id,
                base.aggregate_version,
                base.schema_version,
                base.state_payload,
                "b" * 64,
                base.snapshot_checksum,
                base.created_at,
            )
        )
        != digest
    )
    assert (
        snapshot_checksum(
            OrderSnapshot(
                base.snapshot_id,
                base.order_id,
                base.aggregate_version,
                base.schema_version,
                base.state_payload,
                base.journal_head_checksum,
                base.snapshot_checksum,
                datetime(2026, 7, 10, 1, 2, 4, tzinfo=UTC),
            )
        )
        != digest
    )

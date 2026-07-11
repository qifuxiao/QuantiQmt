from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from quantiqmt.order.application.persistence import (
    ClaimPolicy,
    JournalAppend,
    OrderRegistration,
    OrderRegistrationDraft,
    PersistedOrder,
    canonical_json_bytes,
    deterministic_message_id,
    order_state_payload,
    registration_fingerprint,
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
    first = deterministic_message_id("oms.order_registered.v1", ORDER_ID.value, 1)
    second = deterministic_message_id("oms.order_registered.v1", ORDER_ID.value, 1)
    assert first == second
    assert len(first) == 64
